import os
import io
import requests
from flask import Flask, render_template, request, send_file, jsonify
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import PCMYKColor

app = Flask(__name__)

# --- CONFIGURAÇÕES VIA VARIÁVEIS DE AMBIENTE (DOKPLOY) ---
DIRECTUS_URL = os.environ.get("DIRECTUS_URL")
DIRECTUS_TOKEN = os.environ.get("DIRECTUS_TOKEN")

# Verifica se as variáveis existem (apenas alerta no log)
if not DIRECTUS_URL or not DIRECTUS_TOKEN:
    print("⚠️  ALERTA: Variáveis de Ambiente não configuradas corretamente no Dokploy!")

# Headers padrão
HEADERS = {
    "Authorization": f"Bearer {DIRECTUS_TOKEN}",
    "Content-Type": "application/json"
}

# --- ROTA 1: FRONTEND ---
@app.route('/')
def index():
    try:
        r = requests.get(f"{DIRECTUS_URL}/items/produtos?filter[status][_eq]=published&limit=-1", headers=HEADERS)
        if r.status_code == 200:
            produtos = r.json().get('data', [])
        else:
            print(f"Erro Directus: {r.text}")
            produtos = []
    except Exception as e:
        print(f"Erro conexão: {e}")
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

        r = requests.post(f"{DIRECTUS_URL}/items/produtos", headers=HEADERS, json=novo_produto)

        if r.status_code in [200, 201]:
            return jsonify({"success": True, "data": r.json()})
        else:
            return jsonify({"success": False, "erro": r.text}), 400

    except Exception as e:
        return jsonify({"success": False, "erro": str(e)}), 500

# --- ROTA 3: GERADOR DE PDF (ATUALIZADA) ---
@app.route('/gerar-gabarito', methods=['POST'])
def gerar_gabarito():
    try:
        data = request.json
        largura = float(data.get('largura'))
        altura = float(data.get('altura'))
        nome = data.get('nome', 'Gabarito')
        modo_cor = data.get('cor', 'cmyk')

        buffer = io.BytesIO()
        
        # Cria a página com o tamanho exato do produto
        c = canvas.Canvas(buffer, pagesize=(largura * mm, altura * mm))
        
        # --- ALTERAÇÃO: FUNDO BRANCO E SEM TEXTO ---
        
        # Define a cor BRANCA dependendo do modo
        if modo_cor == 'cmyk':
            # Branco em CMYK (0,0,0,0)
            c.setFillColor(PCMYKColor(0, 0, 0, 0))
            c.setStrokeColor(PCMYKColor(0, 0, 0, 0))
        else:
            # Branco em RGB (1,1,1)
            c.setFillColorRGB(1, 1, 1)
            c.setStrokeColorRGB(1, 1, 1)

        # Desenha o retângulo branco cobrindo tudo (para garantir que não seja transparente)
        c.rect(0, 0, largura * mm, altura * mm, fill=1, stroke=0)

        # OBS: Removida a parte que desenhava o texto (c.drawString)
        
        c.showPage()
        c.save()
        
        buffer.seek(0)
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
