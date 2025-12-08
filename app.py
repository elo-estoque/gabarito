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
        r = requests.get(f"{DIRECTUS_URL}/items/produtos?filter[status][_eq]=published&limit=-1", headers=HEADERS)
        produtos = r.json().get('data', []) if r.status_code == 200 else []
    except:
        produtos = []
    return render_template('index.html', produtos=produtos)

# --- ROTA 2: CADASTRAR PRODUTO (Mantida) ---
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
        # Envia JSON
        r = requests.post(f"{DIRECTUS_URL}/items/produtos", headers={"Authorization": f"Bearer {DIRECTUS_TOKEN}", "Content-Type": "application/json"}, json=novo_produto)
        
        if r.status_code in [200, 201]:
            return jsonify({"success": True})
        return jsonify({"success": False, "erro": r.text}), 400
    except Exception as e:
        return jsonify({"success": False, "erro": str(e)}), 500

# --- ROTA 3: GERAR PDF (COM UPLOAD E CMYK) ---
@app.route('/gerar-gabarito', methods=['POST'])
def gerar_gabarito():
    try:
        # Recebe dados do formulário (Multipart)
        largura = float(request.form.get('largura'))
        altura = float(request.form.get('altura'))
        nome = request.form.get('nome', 'Gabarito')
        modo_cor = request.form.get('cor', 'cmyk')
        salvar_directus = request.form.get('salvar_directus') == 'true'
        
        arquivo_upload = request.files.get('imagem') # O arquivo enviado

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=(largura * cm, altura * cm))

        # 1. Se tiver imagem, processa e coloca no PDF
        if arquivo_upload:
            # Abre a imagem com Pillow
            img = Image.open(arquivo_upload)
            
            # Salva no Directus se solicitado
            if salvar_directus:
                # Rebobina o arquivo para enviar ao Directus
                arquivo_upload.seek(0)
                files = {'file': (arquivo_upload.filename, arquivo_upload, arquivo_upload.content_type)}
                try:
                    # Upload para directus_files
                    requests.post(f"{DIRECTUS_URL}/files", headers=HEADERS, files=files)
                except Exception as e:
                    print(f"Erro ao salvar no Directus: {e}")

            # Conversão de Cor para o PDF
            if modo_cor == 'cmyk':
                # Converte para CMYK real para o PDF
                img = img.convert('CMYK')
            else:
                img = img.convert('RGB')

            # Salva imagem temporária processada para inserir no PDF
            img_buffer = io.BytesIO()
            # PDF exige JPEG para CMYK ou PNG para RGB/Alpha
            format_img = 'JPEG' if modo_cor == 'cmyk' else 'PNG'
            img.save(img_buffer, format=format_img, quality=95)
            img_buffer.seek(0)

            # Desenha a imagem esticada no tamanho total (Fit to Page)
            # preserveAspectRatio=True manteria a proporção, mas aqui vamos preencher
            c.drawImage(
                request.files['imagem'].filename if not salvar_directus else "temp_img", # label dummy
                img_buffer, 
                0, 0, 
                width=largura*cm, 
                height=altura*cm,
                mask='auto'
            )

        # 2. Desenha o Retângulo de Contorno (Gabarito)
        # Se não tiver imagem, fundo branco. Se tiver, transparente em cima.
        if not arquivo_upload:
             if modo_cor == 'cmyk':
                c.setFillColor(PCMYKColor(0,0,0,0))
             else:
                c.setFillColorRGB(1,1,1)
             c.rect(0, 0, largura * cm, altura * cm, fill=1, stroke=0)

        c.showPage()
        c.save()
        
        buffer.seek(0)
        extensao = "CMYK" if modo_cor == 'cmyk' else "RGB"
        tipo = "COM_ARTE" if arquivo_upload else "GABARITO"

        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"{tipo}_{nome}_{extensao}.pdf",
            mimetype='application/pdf'
        )

    except Exception as e:
        return jsonify({"erro": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
