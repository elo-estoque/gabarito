import os
import io
import requests
from flask import Flask, render_template, request, send_file, jsonify
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib.colors import PCMYKColor
# NOVA IMPORTAÇÃO NECESSÁRIA:
from reportlab.lib.utils import ImageReader
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

# --- ROTA 3: GERAR PDF (CORRIGIDA COM ImageReader) ---
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
            # Lê o arquivo para a memória
            imagem_bytes = arquivo_upload.read() 
            
            # --- UPLOAD PRO DIRECTUS ---
            if salvar_directus:
                try:
                    stream_para_directus = io.BytesIO(imagem_bytes)
                    files = {'file': (arquivo_upload.filename, stream_para_directus, arquivo_upload.content_type)}
                    requests.post(f"{DIRECTUS_URL}/files", headers=HEADERS, files=files, timeout=5)
                except Exception as e:
                    print(f"Erro no upload (não crítico): {e}")

            # --- PROCESSAMENTO DA IMAGEM ---
            try:
                stream_para_pillow = io.BytesIO(imagem_bytes)
                img = Image.open(stream_para_pillow)

                # Conversão
                if modo_cor == 'cmyk':
                    img = img.convert('CMYK')
                    format_img = 'JPEG'
                else:
                    img = img.convert('RGB')
                    format_img = 'PNG'

                # Salva processada na memória
                img_buffer_final = io.BytesIO()
                img.save(img_buffer_final, format=format_img, quality=95)
                img_buffer_final.seek(0)

                # --- CORREÇÃO AQUI: ImageReader ---
                # Envolvemos o buffer no ImageReader para o ReportLab não confundir
                imagem_para_pdf = ImageReader(img_buffer_final)

                c.drawImage(
                    imagem_para_pdf, 
                    0, 0, 
                    width=largura*cm, 
                    height=altura*cm,
                    mask='auto'
                )
            except Exception as e_img:
                print(f"Erro imagem: {e_img}")
                c.drawString(1*cm, altura/2*cm, f"Erro na imagem: {str(e_img)}")

        # 3. Se não tiver imagem (Fundo Branco)
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
        print(f"ERRO CRÍTICO: {str(e)}")
        return jsonify({"erro": f"Erro interno: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
