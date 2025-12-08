import os
import io
import requests
from flask import Flask, render_template, request, send_file, jsonify
from reportlab.pdfgen import canvas
# MUDANÇA AQUI: Importando cm ao invés de mm
from reportlab.lib.units import cm
from reportlab.lib.colors import PCMYKColor

app = Flask(__name__)

# --- CONFIGURAÇÕES (Lê do Dokploy) ---
DIRECTUS_URL = os.environ.get("DIRECTUS_URL")
DIRECTUS_TOKEN = os.environ.get("DIRECTUS_TOKEN")

if not DIRECTUS_URL or not DIRECTUS_TOKEN:
    print("⚠️  ALERTA: Variáveis de Ambiente não configuradas!")

HEADERS = {
    "Authorization": f"Bearer {DIRECTUS_TOKEN}",
    "Content-Type": "application/json"
}

@app.route('/')
def index():
    try:
        r = requests.get(f"{DIRECTUS_URL}/items/produtos?filter[status][_eq]=published&limit=-1", headers=HEADERS)
        produtos = r.json().get('data', []) if r.status_code == 200 else []
    except Exception as e:
        print(f"Erro: {e}")
        produtos = []
    return render_template('index.html', produtos=produtos)

@app.route('/cadastrar-produto', methods=['POST'])
def cadastrar_produto():
    data = request.json
    try:
        # Salva o número puro no banco (agora representando cm)
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

@app.route('/gerar-gabarito', methods=['POST'])
def gerar_gabarito():
    try:
        data = request.json
        # O sistema entende que esses valores estão em CM
        largura = float(data.get('largura'))
        altura = float(data.get('altura'))
        nome = data.get('nome', 'Gabarito')
        modo_cor = data.get('cor', 'cmyk')

        buffer = io.BytesIO()
        
        # MUDANÇA AQUI: Multiplica por 'cm' para definir o tamanho correto
        c = canvas.Canvas(buffer, pagesize=(largura * cm, altura * cm))
        
        # Define a cor BRANCA (Fundo Limpo)
        if modo_cor == 'cmyk':
            c.setFillColor(PCMYKColor(0, 0, 0, 0)) # Transparente/Branco
            c.setStrokeColor(PCMYKColor(0, 0, 0, 0))
        else:
            c.setFillColorRGB(1, 1, 1) # Branco RGB
            c.setStrokeColorRGB(1, 1, 1)

        # Desenha o retângulo branco usando a unidade cm
        c.rect(0, 0, largura * cm, altura * cm, fill=1, stroke=0)

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
