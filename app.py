import os
import io
import requests
from flask import Flask, render_template, request, send_file, jsonify
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import PCMYKColor, pink

app = Flask(__name__)

# --- CONFIGURAÇÕES (Puxa do Dokploy ou usa padrão) ---
# Substitua aqui ou use Variáveis de Ambiente no Dokploy
DIRECTUS_URL = os.environ.get("DIRECTUS_URL", "https://api-gabarito.elobrindes.com.br")
DIRECTUS_TOKEN = os.environ.get("DIRECTUS_TOKEN", "4-kfS025X5lFy2k7XVr8DJrfwFJ1RWEO")

# --- ROTA 1: PÁGINA INICIAL (FRONTEND) ---
@app.route('/')
def index():
    # 1. Busca os produtos no Directus para preencher o dropdown
    headers = {"Authorization": f"Bearer {DIRECTUS_TOKEN}"}
    try:
        response = requests.get(f"{DIRECTUS_URL}/items/produtos?filter[status][_eq]=published", headers=headers)
        produtos = response.json().get('data', [])
    except Exception as e:
        print(f"Erro ao conectar Directus: {e}")
        produtos = []

    # 2. Renderiza o HTML passando a lista de produtos
    return render_template('index.html', produtos=produtos)

# --- ROTA 2: GERADOR DE PDF (BACKEND) ---
@app.route('/gerar-gabarito', methods=['POST'])
def gerar_gabarito():
    try:
        data = request.json
        largura = float(data.get('largura'))
        altura = float(data.get('altura'))
        nome = data.get('nome', 'Gabarito')
        modo_cor = data.get('cor', 'cmyk')

        # Cria o buffer de arquivo na memória
        buffer = io.BytesIO()
        
        # Define o tamanho da página PDF exatamente igual ao produto
        c = canvas.Canvas(buffer, pagesize=(largura * mm, altura * mm))
        
        # --- Lógica de Desenho ---
        
        # Fundo (Retângulo do tamanho exato)
        # Se for CMYK para impressão:
        if modo_cor == 'cmyk':
            # Cria uma cor especial (ex: um Ciano puro 100%) para indicar área de impressão
            # (C, M, Y, K, alpha) -> 100% Ciano, 0% outros
            c.setFillColor(PCMYKColor(100, 0, 0, 0, alpha=100))
            c.setStrokeColor(PCMYKColor(100, 0, 0, 0, alpha=100))
        else:
            # RGB para visualização
            c.setFillColorRGB(0, 1, 1) # Ciano RGB
            c.setStrokeColorRGB(0, 1, 1)

        # Desenha o retângulo cobrindo tudo
        c.rect(0, 0, largura * mm, altura * mm, fill=1, stroke=0)

        # Adiciona um texto técnico pequeno
        c.setFillColor(PCMYKColor(0, 0, 0, 100)) if modo_cor == 'cmyk' else c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 8)
        c.drawString(2 * mm, 2 * mm, f"{nome} - {largura}mm x {altura}mm - {modo_cor.upper()}")

        c.showPage()
        c.save()
        
        buffer.seek(0)
        
        # Envia o arquivo de volta para o navegador
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"GABARITO_{nome}_{modo_cor}.pdf",
            mimetype='application/pdf'
        )

    except Exception as e:
        return jsonify({"erro": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
