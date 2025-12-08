import os
import io
import requests
from flask import Flask, render_template, request, send_file, jsonify
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import PCMYKColor

app = Flask(__name__)

# --- CONFIGURAÇÕES VIA VARIÁVEIS DE AMBIENTE ---
# Nenhuma chave fica aqui. Tudo vem do Dokploy.
DIRECTUS_URL = os.environ.get("DIRECTUS_URL")
DIRECTUS_TOKEN = os.environ.get("DIRECTUS_TOKEN")

# Verifica se as variáveis foram carregadas (Debug no log do servidor)
if not DIRECTUS_URL or not DIRECTUS_TOKEN:
    print("⚠️  ALERTA: Variáveis de Ambiente (URL ou TOKEN) não foram encontradas!")

# Headers padrão
HEADERS = {
    "Authorization": f"Bearer {DIRECTUS_TOKEN}",
    "Content-Type": "application/json"
}

# --- ROTA 1: PÁGINA INICIAL ---
@app.route('/')
def index():
    try:
        # Busca produtos (Status = Published)
        r = requests.get(f"{DIRECTUS_URL}/items/produtos?filter[status][_eq]=published&limit=-1", headers=HEADERS)
        
        if r.status_code == 200:
            produtos = r.json().get('data', [])
        else:
            print(f"Erro Directus ({r.status_code}): {r.text}")
            produtos = []
    except Exception as e:
        print(f"Erro de conexão: {e}")
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

# --- ROTA 3: GERADOR DE PDF ---
@app.route('/gerar-gabarito', methods=['POST'])
def gerar_gabarito():
    try:
        data = request.json
        largura = float(data.get('largura'))
        altura = float(data.get('altura'))
        nome = data.get('nome', 'Gabarito')
        modo_cor = data.get('cor', 'cmyk')

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=(largura * mm, altura * mm))
        
        if modo_cor == 'cmyk':
            c.setFillColor(PCMYKColor(100, 0, 0, 0, alpha=100))
            c.setStrokeColor(PCMYKColor(100, 0, 0, 0, alpha=100))
        else:
            c.setFillColorRGB(0, 1, 1)
            c.setStrokeColorRGB(0, 1, 1)

        c.rect(0, 0, largura * mm, altura * mm, fill=1, stroke=0)

        # Texto técnico
        c.setFillColor(PCMYKColor(0, 0, 0, 100)) if modo_cor == 'cmyk' else c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 8)
        c.drawString(2 * mm, 2 * mm, f"{nome} - {largura}mm x {altura}mm - {modo_cor.upper()}")

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
