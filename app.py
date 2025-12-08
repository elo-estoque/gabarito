import os
import io
import requests
from flask import Flask, render_template, request, send_file, jsonify
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib.colors import PCMYKColor
from PIL import Image

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
DIRECTUS_URL = os.environ.get("DIRECTUS_URL")
DIRECTUS_TOKEN = os.environ.get("DIRECTUS_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {DIRECTUS_TOKEN}"
}

# --- ROTA 1: FRONTEND ---
@app.route('/')
def index():
    try:
        if DIRECTUS_URL:
            r = requests.get(f"{DIRECTUS_URL}/items/produtos?filter[status][_eq]=published&limit=-1", headers=HEADERS, timeout=5)
            produtos = r.json().get('data', []) if r.status_code == 200 else []
        else:
            produtos = []
    except Exception as e:
        print(f"Erro ao buscar produtos: {e}")
        produtos = []
    return render_template('index.html', produtos=produtos)

# --- ROTA 2: CADASTRAR PRODUTO ---
@app.route('/cadastrar-produto', methods=['POST'])
def cadastrar_produto():
    data = request.json
    try:
        novo_produto = {
            "status": "published",
            "nome": data.get('nome'),
            "codigo": data.get('codigo'),
            "largura": float(data.get('largura')),
            "altura": float(data.get('altura')),
            "tipo_gabarito": "retangular"
        }
        r = requests.post(f"{DIRECTUS_URL}/items/produtos", headers={"Authorization": f"Bearer {DIRECTUS_TOKEN}", "Content-Type": "application/json"}, json=novo_produto)
        
        if r.status_code in [200, 201]:
            return jsonify({"success": True})
        return jsonify({"success": False, "erro": r.text}), 400
    except Exception as e:
        return jsonify({"success": False, "erro": str(e)}), 500

# --- ROTA 3: GERAR PDF (CORRIGIDA) ---
@app.route('/gerar-gabarito', methods=['POST'])
def gerar_gabarito():
    try:
        # 1. Recebe dados
        largura = float(request.form.get('largura'))
        altura = float(request.form.get('altura'))
        nome = request.form.get('nome', 'Gabarito')
        modo_cor = request.form.get('cor', 'cmyk')
        salvar_directus = request.form.get('salvar_directus') == 'true'
        
        arquivo_upload = request.files.get('imagem')

        # Cria o canvas do PDF
        buffer_pdf = io.BytesIO()
        c = canvas.Canvas(buffer_pdf, pagesize=(largura * cm, altura * cm))

        # 2. Lógica de Imagem (Se houver upload)
        if arquivo_upload and arquivo_upload.filename != '':
            # --- CORREÇÃO DO PONTEIRO: LÊ O ARQUIVO PARA A MEMÓRIA UMA VEZ ---
            # Isso cria uma cópia segura dos dados brutos
            imagem_bytes = arquivo_upload.read() 
            
            # --- PARTE A: UPLOAD PRO DIRECTUS (OPCIONAL) ---
            if salvar_directus:
                try:
                    # Cria um stream novo só para o upload
                    stream_para_directus = io.BytesIO(imagem_bytes)
                    files = {'file': (arquivo_upload.filename, stream_para_directus, arquivo_upload.content_type)}
                    
                    # Tenta enviar. Se der erro, NÃO para o gerador de PDF.
                    print("Tentando upload para Directus...")
                    resp = requests.post(f"{DIRECTUS_URL}/files", headers=HEADERS, files=files, timeout=10)
                    if resp.status_code not in [200, 201]:
                        print(f"Erro no Upload Directus: {resp.text}")
                    else:
                        print("Upload Directus OK")
                except Exception as e_upload:
                    print(f"Falha ao conectar no Directus para upload: {e_upload}")
                    # Segue a vida, não trava o usuário

            # --- PARTE B: PROCESSAMENTO PILLOW ---
            try:
                # Cria um stream novo só para o Pillow
                stream_para_pillow = io.BytesIO(imagem_bytes)
                img = Image.open(stream_para_pillow)

                # Conversão de Cor
                if modo_cor == 'cmyk':
                    img = img.convert('CMYK')
                    format_img = 'JPEG' # PDF prefere JPEG para CMYK
                else:
                    img = img.convert('RGB')
                    format_img = 'PNG' # PNG preserva transparência em RGB

                # Salva a imagem processada em um novo buffer
                img_buffer_final = io.BytesIO()
                img.save(img_buffer_final, format=format_img, quality=95)
                img_buffer_final.seek(0)

                # Desenha no PDF
                c.drawImage(
                    img_buffer_final, 
                    0, 0, 
                    width=largura*cm, 
                    height=altura*cm,
                    mask='auto' # Tenta preservar transparência se houver
                )
            except Exception as e_img:
                print(f"Erro ao processar imagem com Pillow: {e_img}")
                # Se der erro na imagem, gera o PDF branco com o erro escrito (debug visual)
                c.drawString(1*cm, altura/2*cm, f"Erro na imagem: {str(e_img)}")

        # 3. Se não tiver imagem (Gabarito em Branco)
        else:
             if modo_cor == 'cmyk':
                c.setFillColor(PCMYKColor(0,0,0,0))
             else:
                c.setFillColorRGB(1,1,1)
             c.rect(0, 0, largura * cm, altura * cm, fill=1, stroke=0)

        c.showPage()
        c.save()
        
        buffer_pdf.seek(0)
        extensao = "CMYK" if modo_cor == 'cmyk' else "RGB"
        tipo = "COM_ARTE" if arquivo_upload else "GABARITO"

        return send_file(
            buffer_pdf,
            as_attachment=True,
            download_name=f"{tipo}_{nome}_{extensao}.pdf",
            mimetype='application/pdf'
        )

    except Exception as e:
        # LOGA O ERRO REAL NO CONSOLE DO DOKPLOY
        print(f"ERRO CRÍTICO 500: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"erro": f"Erro interno: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
