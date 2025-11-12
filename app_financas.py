import os
import pandas as pd
import matplotlib
matplotlib.use('Agg') # ESSENCIAL para rodar matplotlib em servidor
import matplotlib.pyplot as plt
from datetime import datetime
import time
from flask import Flask, render_template, request, redirect, url_for

# --- Configuração de Caminhos Absolutos ---
# Isso garante que o app encontre os arquivos, não importa como seja executado.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "financas.csv")
STATIC_FOLDER = os.path.join(BASE_DIR, 'static')

# Inicializa a aplicação Flask
app = Flask(__name__)

def carregar_dados():
    """Lê o arquivo CSV e o retorna como um DataFrame pandas."""
    if os.path.exists(CSV_PATH):
        try:
            # Tenta ler com utf-8, que é o padrão de salvamento
            df = pd.read_csv(CSV_PATH, encoding="utf-8")
        except UnicodeDecodeError:
            # Se falhar, tenta com latin1 como fallback
            df = pd.read_csv(CSV_PATH, encoding="latin1")
    else:
        df = pd.DataFrame(columns=["Data", "Tipo", "Categoria", "Descricao", "Valor", "Responsavel"])
    
    # Garante que a coluna 'Valor' seja numérica
    if "Valor" in df.columns:
        df["Valor"] = pd.to_numeric(df["Valor"], errors='coerce').fillna(0)
    
    df.reset_index(inplace=True) # Garante que cada linha tenha um 'index' único para exclusão

    return df

def salvar_dados(df):
    """Salva o DataFrame no arquivo CSV com codificação utf-8."""
    # Prepara o DataFrame para salvar, removendo colunas de índice temporárias
    df_to_save = df.copy()
    cols_to_drop = [col for col in ['index', 'level_0', 'Data_dt', 'Categoria_Normalizada_Filtro', 'Categoria_Normalizada', 'Mes'] if col in df_to_save.columns]
    if cols_to_drop:
        df_to_save.drop(columns=cols_to_drop, inplace=True)
    df_to_save.to_csv(CSV_PATH, index=False, encoding="utf-8")

@app.route('/', methods=['GET', 'POST'])
def index():
    # --- Lógica para ADICIONAR um novo registro (quando o formulário é enviado) ---
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

        df = pd.concat([df, pd.DataFrame([novo_registro])], ignore_index=True)
        salvar_dados(df)
        
        # Redireciona para a página principal para evitar reenvio do formulário
        return redirect(url_for('index'))

    # --- Lógica para EXIBIR a página (quando a página é carregada via GET) ---
    df = carregar_dados()
    
    # --- Lógica de Filtro ---
    filtro_mes_selecionado = request.args.get('filtro_mes', '')
    filtro_responsavel_selecionado = request.args.get('filtro_responsavel', '')
    filtro_categoria_selecionado = request.args.get('filtro_categoria', '')

    # Prepara dados para os dropdowns de filtro ANTES de filtrar o dataframe principal
    meses_disponiveis = []
    responsaveis_disponiveis = []
    categorias_disponiveis = []
    if not df.empty:
        df['Data_dt'] = pd.to_datetime(df['Data'], format='%d-%m-%Y', errors='coerce')
        df.dropna(subset=['Data_dt'], inplace=True)
        meses_disponiveis = sorted(df['Data_dt'].dt.strftime('%Y-%m').unique().tolist(), reverse=True)
        responsaveis_disponiveis = sorted(df['Responsavel'].str.strip().unique().tolist())
        categorias_disponiveis = sorted(df['Categoria'].str.strip().unique().tolist())

    # Aplica os filtros se eles foram selecionados
    df_filtrado = df.copy()
    if not df_filtrado.empty:
        df_filtrado['Categoria_Normalizada_Filtro'] = df_filtrado['Categoria'].str.strip()
        if filtro_mes_selecionado:
            df_filtrado = df_filtrado[df_filtrado['Data_dt'].dt.strftime('%Y-%m') == filtro_mes_selecionado]
        if filtro_responsavel_selecionado:
            df_filtrado = df_filtrado[df_filtrado['Responsavel'].str.strip() == filtro_responsavel_selecionado]
        if filtro_categoria_selecionado:
            df_filtrado = df_filtrado[df_filtrado['Categoria_Normalizada_Filtro'] == filtro_categoria_selecionado]

    # --- Cálculos para o Resumo (baseado nos dados filtrados) ---
    if not df_filtrado.empty:
        total_entradas = df_filtrado[df_filtrado['Tipo'] == 'entrada']['Valor'].sum()
        total_saidas = df_filtrado[df_filtrado['Tipo'] == 'saida']['Valor'].sum()
    else:
        total_entradas = 0
        total_saidas = 0
    saldo_total = total_entradas - total_saidas

    graph1_url, graph2_url = None, None

    # A geração de gráficos e a lista de entradas agora usam o df_filtrado
    if not df_filtrado.empty:
        # Converte a coluna 'Data' para o tipo datetime para análise
        # A coluna 'Data_dt' já foi criada e validada

        # Normaliza a categoria para agrupar corretamente (ex: "lazer" e "Lazer")
        df_filtrado['Categoria_Normalizada'] = df_filtrado['Categoria'].str.strip().str.lower()

        # --- Geração do Gráfico 1: Gastos por Categoria ---
        gastos_por_categoria = df_filtrado[df_filtrado['Tipo'] == 'saida'].groupby('Categoria_Normalizada')['Valor'].sum()
        if not gastos_por_categoria.empty:
            plt.figure(figsize=(10, 6))
            gastos_por_categoria.plot(kind='bar', color='#d9534f')
            plt.title('Gastos por Categoria')
            plt.xlabel('Categoria')
            plt.ylabel('Valor (R$)')
            plt.xticks(rotation=45, ha="right")
            plt.tight_layout()
            # Adiciona um timestamp para evitar cache do navegador
            graph1_filename = f"gastos_categoria_{int(time.time())}.png"
            plt.savefig(os.path.join(STATIC_FOLDER, graph1_filename)) # Usa o caminho absoluto
            plt.close()
            graph1_url = url_for('static', filename=graph1_filename)

        # --- Geração do Gráfico 2: Entradas vs Saídas por Mês ---
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
            graph2_filename = f"entradas_saidas_{int(time.time())}.png"
            plt.savefig(os.path.join(STATIC_FOLDER, graph2_filename)) # Usa o caminho absoluto
            plt.close()
            graph2_url = url_for('static', filename=graph2_filename)
        
        # Prepara todos os registros para exibição na tabela
        # Converte para uma lista de dicionários para o template
        all_entries = df_filtrado.to_dict('records')
    else:
        all_entries = []

    # Renderiza o template HTML, passando as URLs dos gráficos e a tabela
    return render_template('index.html', 
                           graph1_url=graph1_url, 
                           graph2_url=graph2_url,
                           entries=all_entries,
                           total_entradas=total_entradas,
                           total_saidas=total_saidas,
                           saldo_total=saldo_total,
                           meses_disponiveis=meses_disponiveis,
                           responsaveis_disponiveis=responsaveis_disponiveis,
                           filtro_mes_selecionado=filtro_mes_selecionado,
                           filtro_responsavel_selecionado=filtro_responsavel_selecionado,
                           categorias_disponiveis=categorias_disponiveis,
                           filtro_categoria_selecionado=filtro_categoria_selecionado)

@app.route('/delete/<int:record_index>', methods=['POST'])
def delete_record(record_index):
    """Deleta um registro pelo seu índice."""
    df = carregar_dados()
    # O 'record_index' vem do template e corresponde ao 'index' que adicionamos
    if not df.empty and record_index in df.index:
        df = df.drop(record_index)
        salvar_dados(df)
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Esta parte não é executada no PythonAnywhere, apenas localmente.
    if os.path.exists(STATIC_FOLDER):
        for item in os.listdir(STATIC_FOLDER):
            if item.endswith(".png"):
                os.remove(os.path.join(STATIC_FOLDER, item))
    app.run(debug=True)
