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
# Token de ADMIN (Service Role) - Necessário para editar o estoque (cliente só lê)
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

# --- LOGIN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            auth_resp = requests.post(f"{DIRECTUS_URL}/auth/login", json={"email": email, "password": password})
            if auth_resp.status_code == 200:
                data = auth_resp.json()['data']
                access_token = data['access_token']
                
                # Busca dados do usuário (incluindo organização se houver)
                user_resp = requests.get(f"{DIRECTUS_URL}/users/me?fields=*,role.*", headers={"Authorization": f"Bearer {access_token}"})
                
                if user_resp.status_code == 200:
                    user_data = user_resp.json()['data']
                    session['user'] = {
                        'id': user_data['id'],
                        'name': f"{user_data.get('first_name','')} {user_data.get('last_name','')}".strip(),
                        'email': user_data['email']
                    }
                    return redirect(url_for('index'))
            return render_template('login.html', erro="Dados incorretos.")
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
            # Dropdown de produtos
            r = requests.get(f"{DIRECTUS_URL}/items/produtos_catalogo?filter[status][_eq]=published&limit=-1", headers=HEADERS_SYSTEM, timeout=5)
            produtos = r.json().get('data', []) if r.status_code == 200 else []
        else:
            produtos = []
    except:
        produtos = []
    return render_template('index.html', produtos=produtos, usuario=session['user'])

# --- HISTÓRICO ---
@app.route('/api/historico')
@login_required
def get_historico():
    try:
        # Tenta buscar histórico
        r = requests.get(f"{DIRECTUS_URL}/items/historico?sort=-date_created&limit=50", headers=HEADERS_SYSTEM)
        if r.status_code != 200:
             # Fallback para caso tenha criado com letra Maiúscula
             r = requests.get(f"{DIRECTUS_URL}/items/Historico?sort=-date_created&limit=50", headers=HEADERS_SYSTEM)
        return jsonify(r.json())
    except:
        return jsonify({"data": []})

# --- CADASTRO ---
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
        r = requests.post(f"{DIRECTUS_URL}/items/produtos_catalogo", headers=HEADERS_SYSTEM, json=novo_produto)
        if r.status_code in [200, 201]:
            gravar_historico("Cadastrou Produto", f"{data.get('nome')} ({data.get('codigo')})")
            return jsonify({"success": True})
        return jsonify({"success": False, "erro": r.text}), 400
    except Exception as e:
        return jsonify({"success": False, "erro": str(e)}), 500

# --- GERAR PDF (PROCESSAMENTO) ---
@app.route('/gerar-gabarito', methods=['POST'])
@login_required
def gerar_gabarito():
    try:
        largura = float(request.form.get('largura'))
        altura = float(request.form.get('altura'))
        nome = request.form.get('nome', 'Gabarito')
        modo_cor = request.form.get('cor', 'cmyk')
        salvar_directus = request.form.get('salvar_directus') == 'true'
        produto_id = request.form.get('produto_id') # ID DO PRODUTO VINDO DO HTML
        
        # 1. ARTE E PDF
        arquivo_upload = request.files.get('imagem')
        buffer_pdf = io.BytesIO()
        c = canvas.Canvas(buffer_pdf, pagesize=(largura * cm, altura * cm))
        tem_arte = False

        if arquivo_upload and arquivo_upload.filename != '':
            tem_arte = True
            imagem_bytes = arquivo_upload.read() 
            if salvar_directus:
                try:
                    files = {'file': (arquivo_upload.filename, io.BytesIO(imagem_bytes), arquivo_upload.content_type)}
                    requests.post(f"{DIRECTUS_URL}/files", headers=HEADERS_SYSTEM, files=files, timeout=3)
                except: pass

            try:
                img = Image.open(io.BytesIO(imagem_bytes))
                if modo_cor == 'cmyk':
                    img = img.convert('CMYK')
                    format_img = 'JPEG'
                else:
                    img = img.convert('RGB')
                    format_img = 'PNG'
                
                out = io.BytesIO()
                img.save(out, format=format_img, quality=95)
                out.seek(0)
                c.drawImage(ImageReader(out), 0, 0, width=largura*cm, height=altura*cm)
            except: pass
        else:
             if modo_cor == 'cmyk': c.setFillColor(PCMYKColor(0,0,0,0))
             else: c.setFillColorRGB(1,1,1)
             c.rect(0, 0, largura * cm, altura * cm, fill=1, stroke=0)

        c.showPage()
        c.save()
        
        # 2. LÓGICA DE ESTOQUE (PAI E FILHO)
        tipo_acao = "Gerou Prova" if tem_arte else "Baixou Gabarito"
        
        # Só desconta se for Prova (com arte) e tiver ID
        if tem_arte and produto_id:
            descontar_estoque_hierarquico(produto_id)
        
        gravar_historico(tipo_acao, f"{nome} ({modo_cor})")

        buffer_pdf.seek(0)
        extensao = "CMYK" if modo_cor == 'cmyk' else "RGB"
        tipo_nome = "PROVA" if tem_arte else "GABARITO"
        return send_file(buffer_pdf, as_attachment=True, download_name=f"{tipo_nome}_{nome}_{extensao}.pdf", mimetype='application/pdf')

    except Exception as e:
        return jsonify({"erro": f"Erro interno: {str(e)}"}), 500

# --- FUNÇÕES DE CONTROLE E BANCO ---

def gravar_historico(acao, produto):
    try:
        user_name = session.get('user', {}).get('name', 'Sistema')
        requests.post(f"{DIRECTUS_URL}/items/historico", headers=HEADERS_SYSTEM, json={
            "acao": acao, "produto": produto, "usuario": user_name
        })
    except: pass

def obter_organizacao_usuario(user_id):
    """ Busca qual a Organization do usuário atual para filtrar o estoque correto """
    try:
        # No Directus padrão, o campo costuma ser 'organization' ou dentro de 'role' se for customizado.
        # Vou tentar buscar o usuário e ver o campo 'organization' (comum em setups B2B)
        r = requests.get(f"{DIRECTUS_URL}/users/{user_id}?fields=organization", headers=HEADERS_SYSTEM)
        if r.status_code == 200:
            return r.json()['data'].get('organization')
    except:
        pass
    return None

def descontar_estoque_hierarquico(produto_id):
    """
    1. Acha estoque_cliente (Pai) pelo Produto + Organização do Usuário.
    2. Acha estoque_lotes (Filhos) vinculados a esse pai.
    3. Pega o primeiro lote com quantidade > 0.
    4. Desconta 1 do Lote e 1 do Pai.
    """
    try:
        user_id = session['user']['id']
        org_id = obter_organizacao_usuario(user_id)
        
        # Se não achou organização, tenta filtrar só pelo produto (arriscado se tiver múltiplos clientes, mas necessário fallback)
        filtro_org = f"&filter[organization_id][_eq]={org_id}" if org_id else ""
        
        # 1. BUSCA O PAI (Estoque Cliente)
        # Campo 'quantidade_disponivel' conforme print
        url_pai = f"{DIRECTUS_URL}/items/estoque_cliente?filter[produto_id][_eq]={produto_id}{filtro_org}"
        r_pai = requests.get(url_pai, headers=HEADERS_SYSTEM)
        dados_pai = r_pai.json().get('data', [])
        
        if not dados_pai:
            print(f"Estoque PAI não encontrado para Produto {produto_id}")
            return

        estoque_pai = dados_pai[0]
        pai_id = estoque_pai['id']
        qtd_pai_atual = int(estoque_pai.get('quantidade_disponivel', 0)) # Campo da imagem 8731aa
        
        if qtd_pai_atual <= 0:
            print("Estoque total zerado.")
            return

        # 2. BUSCA OS FILHOS (Estoque Lotes)
        # Filtra onde 'estoque_pai_id' é o ID do pai encontrado e quantidade > 0
        # Campo 'estoque_pai_id' e 'quantidade' conforme print 873454
        url_lotes = f"{DIRECTUS_URL}/items/estoque_lotes?filter[estoque_pai_id][_eq]={pai_id}&filter[quantidade][_gt]=0"
        r_lotes = requests.get(url_lotes, headers=HEADERS_SYSTEM)
        lotes = r_lotes.json().get('data', [])

        if not lotes:
            print("Nenhum LOTE com saldo encontrado, apesar do pai ter saldo.")
            return

        # Pega o primeiro lote disponível (FIFO simples)
        lote_alvo = lotes[0]
        lote_id = lote_alvo['id']
        qtd_lote_atual = int(lote_alvo.get('quantidade', 0))

        # 3. ATUALIZA O LOTE (FILHO)
        requests.patch(
            f"{DIRECTUS_URL}/items/estoque_lotes/{lote_id}",
            headers=HEADERS_SYSTEM,
            json={"quantidade": qtd_lote_atual - 1}
        )

        # 4. ATUALIZA O PAI (CLIENTE)
        requests.patch(
            f"{DIRECTUS_URL}/items/estoque_cliente/{pai_id}",
            headers=HEADERS_SYSTEM,
            json={"quantidade_disponivel": qtd_pai_atual - 1}
        )
        
        print(f"SUCESSO: Descontado 1 item do Lote {lote_id} e do Pai {pai_id}")

    except Exception as e:
        print(f"Erro crítico ao atualizar estoque: {e}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
