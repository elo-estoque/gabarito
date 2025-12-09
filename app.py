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
# Este token DEVE ser de Administrador (Service Role) para poder mexer no estoque
# enquanto o usuário comum (CLIENTES B2C) tem permissão apenas de leitura.
DIRECTUS_TOKEN = os.environ.get("DIRECTUS_TOKEN") 

HEADERS_SYSTEM = {
    "Authorization": f"Bearer {DIRECTUS_TOKEN}",
    "Content-Type": "application/json"
}

# --- DECORATOR: Protege as rotas ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- ROTA: LOGIN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            # Autentica o usuário final
            auth_resp = requests.post(f"{DIRECTUS_URL}/auth/login", json={
                "email": email, 
                "password": password
            })
            
            if auth_resp.status_code == 200:
                data = auth_resp.json()['data']
                access_token = data['access_token']
                
                user_resp = requests.get(f"{DIRECTUS_URL}/users/me", headers={
                    "Authorization": f"Bearer {access_token}"
                })
                
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
            return render_template('login.html', erro=f"Erro de conexão: {str(e)}")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- ROTA: FRONTEND (CORRIGIDA) ---
@app.route('/')
@login_required
def index():
    try:
        if DIRECTUS_URL:
            # CORREÇÃO 1: Nome da tabela ajustado para 'produtos_catalogo'
            r = requests.get(f"{DIRECTUS_URL}/items/produtos_catalogo?filter[status][_eq]=published&limit=-1", headers=HEADERS_SYSTEM, timeout=5)
            produtos = r.json().get('data', []) if r.status_code == 200 else []
        else:
            produtos = []
    except Exception as e:
        print(f"Erro ao buscar produtos: {e}")
        produtos = []
    
    return render_template('index.html', produtos=produtos, usuario=session['user'])

# --- ROTA: HISTÓRICO ---
@app.route('/api/historico')
@login_required
def get_historico():
    try:
        # Busca na tabela 'historico'. Lembre-se de criar esta tabela no Directus!
        r = requests.get(f"{DIRECTUS_URL}/items/historico?sort=-date_created&limit=50", headers=HEADERS_SYSTEM)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"data": []})

# --- ROTA: CADASTRAR PRODUTO ---
@app.route('/cadastrar-produto', methods=['POST'])
@login_required
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
        # CORREÇÃO 2: Ajustado para 'produtos_catalogo'
        r = requests.post(f"{DIRECTUS_URL}/items/produtos_catalogo", headers=HEADERS_SYSTEM, json=novo_produto)
        
        if r.status_code in [200, 201]:
            gravar_historico("Cadastrou Produto", f"{data.get('nome')} ({data.get('codigo')})")
            return jsonify({"success": True})
        return jsonify({"success": False, "erro": r.text}), 400
    except Exception as e:
        return jsonify({"success": False, "erro": str(e)}), 500

# --- ROTA: GERAR PDF (PROCESSAMENTO CENTRAL) ---
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

        # === AUTOMAÇÃO DE ESTOQUE (Exemplo) ===
        # Aqui é onde o Python (Admin) desconta o estoque, mesmo que o usuário não tenha permissão.
        # Se você tiver o ID do produto vindo do front, pode descomentar e ajustar:
        # id_produto = request.form.get('id_produto')
        # if id_produto:
        #     atualizar_estoque(id_produto, -1)

        buffer_pdf = io.BytesIO()
        c = canvas.Canvas(buffer_pdf, pagesize=(largura * cm, altura * cm))

        tem_arte = False
        if arquivo_upload and arquivo_upload.filename != '':
            tem_arte = True
            imagem_bytes = arquivo_upload.read() 
            
            if salvar_directus:
                try:
                    stream_para_directus = io.BytesIO(imagem_bytes)
                    files = {'file': (arquivo_upload.filename, stream_para_directus, arquivo_upload.content_type)}
                    # Salva usando token de Admin (HEADERS_SYSTEM)
                    requests.post(f"{DIRECTUS_URL}/files", headers=HEADERS_SYSTEM, files=files, timeout=5)
                except: pass

            try:
                stream_para_pillow = io.BytesIO(imagem_bytes)
                img = Image.open(stream_para_pillow)
                if modo_cor == 'cmyk':
                    img = img.convert('CMYK')
                    format_img = 'JPEG'
                else:
                    img = img.convert('RGB')
                    format_img = 'PNG'

                img_buffer_final = io.BytesIO()
                img.save(img_buffer_final, format=format_img, quality=95)
                img_buffer_final.seek(0)
                imagem_para_pdf = ImageReader(img_buffer_final)

                c.drawImage(imagem_para_pdf, 0, 0, width=largura*cm, height=altura*cm, mask='auto')
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
        
        # LOG
        tipo_acao = "Gerou Prova" if tem_arte else "Baixou Gabarito"
        detalhes = f"{nome} - {largura}x{altura}cm ({modo_cor.upper()})"
        gravar_historico(tipo_acao, detalhes)

        buffer_pdf.seek(0)
        extensao = "CMYK" if modo_cor == 'cmyk' else "RGB"
        tipo = "PROVA" if tem_arte else "GABARITO"

        return send_file(buffer_pdf, as_attachment=True, download_name=f"{tipo}_{nome}_{extensao}.pdf", mimetype='application/pdf')

    except Exception as e:
        return jsonify({"erro": f"Erro interno: {str(e)}"}), 500

# --- FUNÇÕES AUXILIARES ---
def gravar_historico(acao, produto):
    try:
        usuario_nome = session.get('user', {}).get('name', 'Desconhecido')
        payload = {
            "acao": acao,
            "produto": produto,
            "usuario": usuario_nome
            # data_created é automático
        }
        # Grava usando token Admin, usuário não precisa ter permissão de escrita se for bloqueado
        requests.post(f"{DIRECTUS_URL}/items/historico", headers=HEADERS_SYSTEM, json=payload)
    except Exception as e:
        print(f"Erro ao salvar histórico: {e}")

# Exemplo de função para baixar estoque automaticamente
def atualizar_estoque(produto_id, quantidade_delta):
    try:
        # Primeiro pega o estoque atual
        r = requests.get(f"{DIRECTUS_URL}/items/produtos_catalogo/{produto_id}", headers=HEADERS_SYSTEM)
        if r.status_code == 200:
            estoque_atual = r.json()['data'].get('estoque', 0)
            novo_estoque = estoque_atual + quantidade_delta
            
            # Atualiza
            requests.patch(f"{DIRECTUS_URL}/items/produtos_catalogo/{produto_id}", 
                         headers=HEADERS_SYSTEM, 
                         json={"estoque": novo_estoque})
    except Exception as e:
        print(f"Erro ao atualizar estoque: {e}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
