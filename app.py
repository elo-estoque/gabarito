import os
import io
import requests
import datetime
from flask import Flask, render_template, request, send_file, jsonify, session, redirect, url_for
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib.colors import PCMYKColor
from reportlab.lib.utils import ImageReader
from PIL import Image
from functools import wraps

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
app.secret_key = os.environ.get("SECRET_KEY", "chave_super_secreta_elo_brindes_2024")

DIRECTUS_URL = os.environ.get("DIRECTUS_URL")
DIRECTUS_TOKEN = os.environ.get("DIRECTUS_TOKEN")

HEADERS_SYSTEM = {
    "Authorization": f"Bearer {DIRECTUS_TOKEN}",
    "Content-Type": "application/json"
}

# --- DECORATOR ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- ROTAS DE LOGIN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            auth_resp = requests.post(f"{DIRECTUS_URL}/auth/login", json={"email": email, "password": password})
            if auth_resp.status_code == 200:
                data = auth_resp.json()['data']
                user_resp = requests.get(f"{DIRECTUS_URL}/users/me", headers={"Authorization": f"Bearer {data['access_token']}"})
                if user_resp.status_code == 200:
                    user_data = user_resp.json()['data']
                    session['user'] = {
                        'id': user_data['id'],
                        'name': f"{user_data.get('first_name','')} {user_data.get('last_name','')}".strip(),
                        'email': user_data['email']
                    }
                    return redirect(url_for('index'))
            return render_template('login.html', erro="E-mail ou senha incorretos.")
        except Exception as e:
            return render_template('login.html', erro=f"Erro: {str(e)}")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- FRONTEND ---
@app.route('/')
@login_required
def index():
    try:
        if DIRECTUS_URL:
            r = requests.get(f"{DIRECTUS_URL}/items/produtos?filter[status][_eq]=published&limit=-1", headers=HEADERS_SYSTEM, timeout=5)
            produtos = r.json().get('data', []) if r.status_code == 200 else []
        else:
            produtos = []
    except: produtos = []
    return render_template('index.html', produtos=produtos, usuario=session['user'])

# --- HISTÓRICO ---
@app.route('/api/historico')
@login_required
def get_historico():
    try:
        r = requests.get(f"{DIRECTUS_URL}/items/historico?sort=-date_created&limit=50", headers=HEADERS_SYSTEM)
        return jsonify(r.json())
    except: return jsonify({"data": []})

# --- CADASTRO ---
@app.route('/cadastrar-produto', methods=['POST'])
@login_required
def cadastrar_produto():
    data = request.json
    try:
        novo = {
            "status": "published", "nome": data.get('nome'), "codigo": data.get('codigo'),
            "largura": float(data.get('largura')), "altura": float(data.get('altura')), "tipo_gabarito": "retangular"
        }
        r = requests.post(f"{DIRECTUS_URL}/items/produtos", headers=HEADERS_SYSTEM, json=novo)
        if r.status_code in [200, 201]:
            gravar_historico("Cadastrou Produto", f"{data.get('nome')} ({data.get('codigo')})")
            return jsonify({"success": True})
        return jsonify({"success": False, "erro": r.text}), 400
    except Exception as e: return jsonify({"success": False, "erro": str(e)}), 500

# --- GERADOR DE PDF (CORRIGIDO PARA COREL/CMYK) ---
@app.route('/gerar-gabarito', methods=['POST'])
@login_required
def gerar_gabarito():
    try:
        largura = float(request.form.get('largura'))
        altura = float(request.form.get('altura'))
        nome = request.form.get('nome', 'Gabarito')
        modo_cor = request.form.get('cor', 'cmyk')
        salvar_directus = request.form.get('salvar_directus') == 'true'
        arquivo_upload = request.files.get('imagem')

        buffer_pdf = io.BytesIO()
        c = canvas.Canvas(buffer_pdf, pagesize=(largura * cm, altura * cm))

        tem_arte = False
        if arquivo_upload and arquivo_upload.filename != '':
            tem_arte = True
            imagem_bytes = arquivo_upload.read() 
            
            if salvar_directus:
                try:
                    stream_dir = io.BytesIO(imagem_bytes)
                    files = {'file': (arquivo_upload.filename, stream_dir, arquivo_upload.content_type)}
                    requests.post(f"{DIRECTUS_URL}/files", headers=HEADERS_SYSTEM, files=files, timeout=5)
                except: pass

            try:
                stream_pillow = io.BytesIO(imagem_bytes)
                img = Image.open(stream_pillow)

                # === CORREÇÃO DA TELA PRETA NO COREL ===
                # Se a imagem tiver transparência (Canal Alpha), nós achatamos ela contra um fundo branco.
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    # Garante conversão para RGBA primeiro para ler a máscara
                    img = img.convert('RGBA')
                    # Cria um fundo branco do mesmo tamanho
                    fundo_branco = Image.new('RGB', img.size, (255, 255, 255))
                    # Cola a imagem original sobre o fundo branco usando o canal alpha como máscara
                    fundo_branco.paste(img, mask=img.split()[3])
                    img = fundo_branco
                else:
                    # Se não tem transparência, converte para RGB padrão
                    img = img.convert('RGB')

                # Agora converte para CMYK ou mantém RGB
                if modo_cor == 'cmyk':
                    img = img.convert('CMYK')
                    format_img = 'JPEG' # CMYK funciona melhor salvo como JPEG dentro do PDF
                else:
                    format_img = 'PNG'

                img_buffer_final = io.BytesIO()
                # Salva com qualidade máxima
                img.save(img_buffer_final, format=format_img, quality=100, dpi=(300, 300))
                img_buffer_final.seek(0)
                
                imagem_para_pdf = ImageReader(img_buffer_final)
                c.drawImage(imagem_para_pdf, 0, 0, width=largura*cm, height=altura*cm)
            except Exception as e:
                c.drawString(1*cm, altura/2*cm, f"Erro img: {str(e)}")
        else:
             if modo_cor == 'cmyk':
                c.setFillColor(PCMYKColor(0,0,0,0))
             else:
                c.setFillColorRGB(1,1,1)
             c.rect(0, 0, largura * cm, altura * cm, fill=1, stroke=0)

        c.showPage()
        c.save()
        
        tipo_acao = "Gerou Prova" if tem_arte else "Baixou Gabarito"
        gravar_historico(tipo_acao, f"{nome} ({modo_cor.upper()})")

        buffer_pdf.seek(0)
        ext = "CMYK" if modo_cor == 'cmyk' else "RGB"
        return send_file(buffer_pdf, as_attachment=True, download_name=f"Prova_{nome}_{ext}.pdf", mimetype='application/pdf')

    except Exception as e:
        print(f"ERRO: {e}")
        return jsonify({"erro": str(e)}), 500

def gravar_historico(acao, produto):
    try:
        user = session.get('user', {}).get('name', 'Anonimo')
        requests.post(f"{DIRECTUS_URL}/items/historico", headers=HEADERS_SYSTEM, json={"acao": acao, "produto": produto, "usuario": user})
    except: pass

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
