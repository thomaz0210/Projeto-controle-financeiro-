import os
import pandas as pd
import matplotlib # type: ignore
matplotlib.use('Agg') # ESSENCIAL para rodar matplotlib em servidor
import matplotlib.pyplot as plt
from datetime import datetime
import time
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# --- Configuração de Caminhos Absolutos ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data") # Pasta para os CSVs dos usuários
STATIC_FOLDER = os.path.join(BASE_DIR, 'static')

# Garante que as pastas de dados e estática existam
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)

# Inicializa a aplicação Flask
app = Flask(__name__) 
app.secret_key = 'dflk89-34jk2-fjkd-99dk' # Chave secreta para a sessão
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'users.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login' # Redireciona para a rota 'login' se o usuário não estiver logado
login_manager.login_message = "Por favor, faça login para acessar esta página."

# --- Modelo de Usuário para o Banco de Dados ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    account_name = db.Column(db.String(80), nullable=False) # Ex: 'conta_casal', 'conta_joao'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Funções de Manipulação de Dados (CSV) ---
def get_user_csv_path():
    """Retorna o caminho absoluto para o arquivo CSV do usuário logado."""
    if current_user.is_authenticated:
        return os.path.join(DATA_DIR, f"{current_user.account_name}.csv")
    return None

def carregar_dados():
    """Carrega os dados do arquivo CSV específico da conta do usuário."""
    csv_path = get_user_csv_path()
    if csv_path and os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="latin1")
    else:
        df = pd.DataFrame(columns=["Data", "Tipo", "Categoria", "Descricao", "Valor", "Responsavel"])
    
    if "Valor" in df.columns:
        df["Valor"] = pd.to_numeric(df["Valor"], errors='coerce').fillna(0)
    
    return df

def salvar_dados(df):
    """Salva o DataFrame modificado de volta no arquivo CSV da conta do usuário."""
    csv_path = get_user_csv_path()
    if csv_path:
        cols_to_drop = ['index', 'Data_dt', 'Categoria_Normalizada_Filtro', 'Categoria_Normalizada', 'Mes']
        df_to_save = df.drop(columns=[col for col in cols_to_drop if col in df.columns], errors='ignore')
        df_to_save.to_csv(csv_path, index=False, encoding="utf-8")

# --- Rotas de Autenticação (Login, Logout, Registro) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha inválidos.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        account_type = request.form['account_type']
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Este nome de usuário já existe. Por favor, escolha outro.')
            return redirect(url_for('register'))

        if account_type == 'individual':
            account_name = f"conta_{username.lower()}"
        else: # shared
            account_name = request.form.get('account_name')
            if not account_name:
                flash('Para conta compartilhada, o nome da conta é obrigatório.')
                return redirect(url_for('register'))

        new_user = User(username=username, account_name=account_name)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Conta criada com sucesso! Por favor, faça login.')
        return redirect(url_for('login'))
        
    return render_template('register.html')

# --- Rota Principal da Aplicação ---
@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        df = carregar_dados()
        novo_registro = {
            "Data": datetime.now().strftime("%d-%m-%Y"),
            "Tipo": request.form['Tipo'],
            "Categoria": request.form['Categoria'].strip(),
            "Descricao": request.form['Descricao'].strip(),
            "Valor": float(request.form['Valor'].strip().replace(",", ".")),
            "Responsavel": request.form['Responsavel'].strip()
        }
        df = pd.concat([df, pd.DataFrame([novo_registro], columns=df.columns)], ignore_index=True)
        salvar_dados(df)
        return redirect(url_for('index'))

    df = carregar_dados()
    df.reset_index(inplace=True)
    
    filtro_mes_selecionado = request.args.get('filtro_mes', '')
    filtro_responsavel_selecionado = request.args.get('filtro_responsavel', '')
    filtro_categoria_selecionado = request.args.get('filtro_categoria', '')

    meses_disponiveis, responsaveis_disponiveis, categorias_disponiveis = [], [], []
    if not df.empty:
        df['Data_dt'] = pd.to_datetime(df['Data'], format='%d-%m-%Y', errors='coerce')
        df.dropna(subset=['Data_dt'], inplace=True)
        meses_disponiveis = sorted(df['Data_dt'].dt.strftime('%Y-%m').unique().tolist(), reverse=True)
        responsaveis_disponiveis = sorted(df['Responsavel'].str.strip().unique().tolist())
        categorias_disponiveis = sorted(df['Categoria'].str.strip().unique().tolist())

    df_filtrado = df.copy()
    if not df_filtrado.empty:
        df_filtrado['Categoria_Normalizada_Filtro'] = df_filtrado['Categoria'].str.strip()
        if filtro_mes_selecionado:
            df_filtrado = df_filtrado[df_filtrado['Data_dt'].dt.strftime('%Y-%m') == filtro_mes_selecionado]
        if filtro_responsavel_selecionado:
            df_filtrado = df_filtrado[df_filtrado['Responsavel'].str.strip() == filtro_responsavel_selecionado]
        if filtro_categoria_selecionado:
            df_filtrado = df_filtrado[df_filtrado['Categoria_Normalizada_Filtro'] == filtro_categoria_selecionado]

    total_entradas = df_filtrado[df_filtrado['Tipo'] == 'entrada']['Valor'].sum() if not df_filtrado.empty else 0
    total_saidas = df_filtrado[df_filtrado['Tipo'] == 'saida']['Valor'].sum() if not df_filtrado.empty else 0
    saldo_total = total_entradas - total_saidas

    graph1_url, graph2_url = None, None
    all_entries = []

    if not df_filtrado.empty:
        df_filtrado['Categoria_Normalizada'] = df_filtrado['Categoria'].str.strip().str.lower()
        gastos_por_categoria = df_filtrado[df_filtrado['Tipo'] == 'saida'].groupby('Categoria_Normalizada')['Valor'].sum()
        if not gastos_por_categoria.empty:
            plt.figure(figsize=(10, 6))
            gastos_por_categoria.plot(kind='bar', color='#d9534f')
            plt.title('Gastos por Categoria')
            plt.xlabel('Categoria')
            plt.ylabel('Valor (R$)')
            plt.xticks(rotation=45, ha="right")
            plt.tight_layout()
            graph1_filename = f"gastos_categoria_{current_user.id}_{int(time.time())}.png"
            plt.savefig(os.path.join(STATIC_FOLDER, graph1_filename))
            plt.close()
            graph1_url = url_for('static', filename=graph1_filename)

        df_filtrado['Mes'] = df_filtrado['Data_dt'].dt.to_period('M').astype(str)
        entradas_saidas_por_mes = df_filtrado.groupby(['Mes', 'Tipo'])['Valor'].sum().unstack().fillna(0)
        if not entradas_saidas_por_mes.empty:
            plt.figure(figsize=(12, 6))
            entradas_saidas_por_mes.plot(kind='bar', figsize=(12, 6), color=['#5cb85c', '#d9534f'])
            plt.title('Entradas vs. Saídas por Mês')
            plt.xlabel('Mês')
            plt.ylabel('Valor (R$)')
            plt.xticks(rotation=45, ha="right")
            plt.legend(['Entrada', 'Saída'])
            plt.tight_layout()
            graph2_filename = f"entradas_saidas_{current_user.id}_{int(time.time())}.png"
            plt.savefig(os.path.join(STATIC_FOLDER, graph2_filename))
            plt.close()
            graph2_url = url_for('static', filename=graph2_filename)
        
        all_entries = df_filtrado.to_dict('records')

    return render_template('index.html', 
                           graph1_url=graph1_url, graph2_url=graph2_url,
                           entries=all_entries,
                           total_entradas=total_entradas, total_saidas=total_saidas, saldo_total=saldo_total,
                           meses_disponiveis=meses_disponiveis, responsaveis_disponiveis=responsaveis_disponiveis,
                           filtro_mes_selecionado=filtro_mes_selecionado, filtro_responsavel_selecionado=filtro_responsavel_selecionado,
                           categorias_disponiveis=categorias_disponiveis, filtro_categoria_selecionado=filtro_categoria_selecionado)

@app.route('/delete/<int:record_index>', methods=['POST'])
@login_required
def delete_record(record_index):
    """Deleta um registro pelo seu índice."""
    df = carregar_dados()
    if not df.empty:
        df.reset_index(inplace=True)
        if record_index in df['index'].values:
            df = df[df['index'] != record_index]
            salvar_dados(df)
    return redirect(url_for('index'))

# --- Função para criar o banco de dados ---
def create_database(app):
    with app.app_context():
        db.create_all()
        print("Banco de dados 'users.db' criado com sucesso!")

if __name__ == '__main__':
    create_database(app) # Cria o banco de dados se não existir
    # Limpa gráficos antigos ao iniciar localmente
    if os.path.exists(STATIC_FOLDER):
        for item in os.listdir(STATIC_FOLDER):
            if item.endswith(".png"):
                os.remove(os.path.join(STATIC_FOLDER, item))
    app.run(debug=True)
