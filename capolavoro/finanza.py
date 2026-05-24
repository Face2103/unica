import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import feedparser
import time
import requests
import datetime
import sqlite3
import uuid

# --- CONFIGURAZIONE PROGETTO ---
st.set_page_config(page_title="Quantum Trader Pro", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")

# --- STYLE ENGINE (CSS PRO MIGLIORATO E ANIMATO) ---
st.markdown("""
    <style>
    .stApp { background-color: #0b0e14; font-family: 'Inter', sans-serif; }
    div[data-baseweb="tab-list"] { background-color: #131722; border-radius: 15px; padding: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.6); margin-bottom: 20px; }
    div[data-baseweb="tab"] { font-size: 1.1rem; font-weight: bold; color: #888; transition: all 0.3s; }
    div[aria-selected="true"] { color: #00e5ff !important; background-color: rgba(0, 229, 255, 0.1); border-radius: 10px; box-shadow: inset 0 0 10px rgba(0, 229, 255, 0.2); }
    .search-container { background: #1c212c; padding: 20px; border-radius: 15px; border: 1px solid #2a2e39; box-shadow: 0 5px 20px rgba(0,0,0,0.5); margin-bottom: 20px; }
    .live-price-glow { font-size: 3.5rem; font-weight: 800; color: #ffffff; text-shadow: 0 0 25px rgba(0, 255, 136, 0.6); margin: 0; padding: 0; line-height: 1; }
    .live-price-red { text-shadow: 0 0 25px rgba(255, 75, 75, 0.6); }
    .news-link { text-decoration: none; color: inherit; transition: transform 0.3s ease; display: block; }
    .news-link:hover { transform: translateY(-8px); }
    .news-card { background: linear-gradient(145deg, #161b22, #0d1117); border-radius: 16px; padding: 0; margin-bottom: 20px; border: 1px solid #30363d; height: 380px; overflow: hidden; transition: border-color 0.3s; }
    .news-card:hover { border-color: #00e5ff; box-shadow: 0 0 20px rgba(0, 229, 255, 0.2); }
    .news-img { width: 100%; height: 180px; object-fit: cover; border-bottom: 1px solid #30363d; }
    .news-content { padding: 15px; }
    .quantum-card { background: linear-gradient(135deg, #131722 0%, #1c212c 100%); padding: 25px; border-radius: 20px; border: 1px solid #2a2e39; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
    .buy-signal { color: #00ff88; font-weight: 800; font-size: 1.5rem; text-shadow: 0 0 15px rgba(0,255,136,0.4); }
    .sell-signal { color: #ff4b4b; font-weight: 800; font-size: 1.5rem; text-shadow: 0 0 15px rgba(255,75,75,0.4); }
    .hold-signal { color: #ffcc00; font-weight: 800; font-size: 1.5rem; text-shadow: 0 0 15px rgba(255,204,0,0.4); }
    .reasoning-text { font-size: 0.95rem; color: #a3a8b0; margin-top: 15px; border-top: 1px solid #2a2e39; padding-top: 15px; }
    .live-pnl-box { background: rgba(0,0,0,0.3); padding: 10px; border-radius: 10px; margin-bottom: 15px; border: 1px solid #30363d; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# --- GESTIONE ACCOUNT UTENTI ---
if 'account_id' not in st.session_state:
    if 'id' in st.query_params:
        st.session_state.account_id = st.query_params['id']
    else:
        new_id = str(uuid.uuid4())[:8].upper()
        st.session_state.account_id = new_id
        st.query_params['id'] = new_id

with st.sidebar:
    st.markdown("### 🔑 Il Tuo Account")
    user_input = st.text_input("ID Conto Personale:", value=st.session_state.account_id)
    if user_input and user_input != st.session_state.account_id:
        st.session_state.account_id = user_input
        st.query_params['id'] = user_input
        st.session_state.initialized = False
        st.rerun()
    st.caption("Il tuo ID è unico. Salvalo per non perdere il tuo portafoglio.")
    st.divider()

# --- GESTIONE DATABASE SQLITE ---
DB_FILE = 'quantum_multiusers.db'

def get_db_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS user (user_id TEXT PRIMARY KEY, balance REAL, pnl REAL, current_month INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS portfolio (user_id TEXT, ticker TEXT, qty REAL, avg_price REAL, PRIMARY KEY (user_id, ticker))')
    c.execute('CREATE TABLE IF NOT EXISTS pending_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, ticker TEXT, type TEXT, target_price REAL, qty REAL)')
    conn.commit()
    conn.close()

def load_state_from_db():
    uid = st.session_state.account_id
    conn = get_db_connection()
    c = conn.cursor()
    user = c.execute('SELECT balance, pnl, current_month FROM user WHERE user_id=?', (uid,)).fetchone()
    real_month = datetime.datetime.now().month
    
    if not user:
        c.execute('INSERT INTO user (user_id, balance, pnl, current_month) VALUES (?, 10000.0, 0.0, ?)', (uid, real_month))
        conn.commit()
        st.session_state.balance, st.session_state.monthly_pnl, st.session_state.current_month = 10000.0, 0.0, real_month
    else:
        if user[2] != real_month:
            c.execute('UPDATE user SET pnl=0.0, current_month=? WHERE user_id=?', (real_month, uid))
            conn.commit()
            st.session_state.monthly_pnl = 0.0
        else:
            st.session_state.monthly_pnl = user[1]
        st.session_state.balance, st.session_state.current_month = user[0], real_month
    
    st.session_state.portfolio = {row[0]: {'qty': row[1], 'avg_price': row[2]} for row in c.execute('SELECT ticker, qty, avg_price FROM portfolio WHERE user_id=?', (uid,)).fetchall()}
    st.session_state.pending_orders = [{'id': row[0], 'ticker': row[1], 'type': row[2], 'target_price': row[3], 'qty': row[4]} for row in c.execute('SELECT id, ticker, type, target_price, qty FROM pending_orders WHERE user_id=?', (uid,)).fetchall()]
    conn.close()

def save_transaction_to_db(ticker=None):
    uid = st.session_state.account_id
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE user SET balance=?, pnl=? WHERE user_id=?', (st.session_state.balance, st.session_state.monthly_pnl, uid))
    if ticker:
        if ticker in st.session_state.portfolio:
            p = st.session_state.portfolio[ticker]
            c.execute('INSERT OR REPLACE INTO portfolio (user_id, ticker, qty, avg_price) VALUES (?, ?, ?, ?)', (uid, ticker, p['qty'], p['avg_price']))
        else:
            c.execute('DELETE FROM portfolio WHERE user_id=? AND ticker=?', (uid, ticker))
    conn.commit()
    conn.close()

def add_pending_order(ticker, order_type, target_price, qty):
    uid = st.session_state.account_id
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO pending_orders (user_id, ticker, type, target_price, qty) VALUES (?, ?, ?, ?, ?)', (uid, ticker, order_type, target_price, qty))
    conn.commit()
    conn.close()
    load_state_from_db()

def remove_pending_order(order_id):
    uid = st.session_state.account_id
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('DELETE FROM pending_orders WHERE id=? AND user_id=?', (order_id, uid))
    conn.commit()
    conn.close()
    load_state_from_db()

init_db()
if 'initialized' not in st.session_state or not st.session_state.initialized:
    load_state_from_db()
    if 'active_ticker' not in st.session_state:
        st.session_state.active_ticker = "BTC-USD - Bitcoin"
    st.session_state.initialized = True

# --- FUNZIONI DI DATI LIVE E RICERCA ---
@st.cache_data(ttl=3600)
def search_yahoo_finance(query):
    if not query: return []
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=5"
        res = requests.get(url, headers=headers, timeout=2).json()
        suggestions = []
        for q in res.get('quotes', []):
            symbol = q.get('symbol', '')
            name = q.get('shortname', q.get('longname', symbol))
            if symbol: suggestions.append(f"{symbol} - {name}")
        return suggestions if suggestions else [f"{query.upper()} - Asset"]
    except:
        return [f"{query.upper()} - Asset"]

def get_true_realtime_data(ticker_full):
    ticker_clean = ticker_full.split(" - ")[0].strip()
    p_live, prev_close = 0.0, 0.0
    
    if any(x in ticker_clean for x in ["BTC", "ETH", "-USD", "DOGE", "SOL"]):
        symbol = ticker_clean.replace("-USD", "USDT").replace("-", "").upper()
        if not symbol.endswith("USDT") and not "=" in symbol: symbol += "USDT"
        try:
            res_live = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=1.5).json()
            res_24h = requests.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}", timeout=1.5).json()
            if 'price' in res_live: 
                return float(res_live['price']), float(res_24h.get('prevClosePrice', res_live['price']))
        except: pass 

    try:
        tk = yf.Ticker(ticker_clean)
        info = tk.fast_info
        p_live = float(info.get('lastPrice', 0.0))
        prev_close = float(info.get('previousClose', 0.0))
        if p_live > 0: return p_live, prev_close
            
        hist = tk.history(period="2d")
        if not hist.empty:
            p_live = float(hist['Close'].iloc[-1])
            prev_close = float(hist['Close'].iloc[0] if len(hist)>1 else hist['Open'].iloc[0])
            return p_live, prev_close
    except: pass
    return 0.0, 0.0

@st.cache_data(ttl=30)
def get_chart_data(ticker_full, period="1D"):
    ticker_clean = ticker_full.split(" - ")[0].strip()
    
    map_p = {
        "1D": ("5d", "15m"), 
        "1M": ("1mo", "1d"), 
        "MAX": ("max", "1wk")
    }
    try:
        data = yf.Ticker(ticker_clean).history(period=map_p[period][0], interval=map_p[period][1])
        return data
    except:
        return pd.DataFrame()

def format_price(price):
    if price < 1: return f"{price:,.6f}"
    elif price < 1000: return f"{price:,.4f}"
    else: return f"{price:,.2f}"

# --- FUNZIONE CREAZIONE GRAFICO PROFESSIONALE A RETTE BICOLORE ---
def create_dynamic_chart(df, chart_ind="Nessuno"):
    """
    Crea il grafico a rette continue proporzionate.
    Le rette cambiano colore (verde sale, rosso scende).
    """
    rows = 2 if chart_ind != "Nessuno" else 1
    row_heights = [0.75, 0.25] if rows == 2 else [1]
    
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, 
                        row_heights=row_heights, vertical_spacing=0.03)
    
    # Convertiamo l'indice in stringhe per eliminare i buchi degli orari di chiusura
    str_index = df.index.strftime('%Y-%m-%d %H:%M')

    cl_vals, dt_vals = df['Close'].values, str_index
    xu, yu, xd, yd = [], [], [], []
    
    # 1. Logica Grafico a Rette Bicolore
    if len(cl_vals) > 2:
        for i in range(1, len(cl_vals)):
            if cl_vals[i] >= cl_vals[i-1]:
                xu.extend([dt_vals[i-1], dt_vals[i], None])
                yu.extend([cl_vals[i-1], cl_vals[i], None])
            else:
                xd.extend([dt_vals[i-1], dt_vals[i], None])
                yd.extend([cl_vals[i-1], cl_vals[i], None])

        # Segmenti bicolore ben visibili (senza riempimento per auto-scalare le Y al massimo)
        fig.add_trace(go.Scatter(x=xu, y=yu, mode='lines', line=dict(color="#00ff88", width=3.5), name="Rialzo", showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=xd, y=yd, mode='lines', line=dict(color="#ff4b4b", width=3.5), name="Ribasso", showlegend=False), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(x=str_index, y=df['Close'], mode='lines', line=dict(color="#00e5ff", width=3.5), name="Prezzo"), row=1, col=1)
    
    # 2. Gestione Indicatori
    if chart_ind == "RSI" and 'RSI' in df.columns:
        fig.add_trace(go.Scatter(x=str_index, y=df['RSI'], line=dict(color='#e0e0e0', width=1.5), name="RSI"), row=2, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="#ff4b4b", line_width=1, row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="#00ff88", line_width=1, row=2, col=1)
    elif chart_ind == "Volumi" and 'Volume' in df.columns:
        if 'Open' in df.columns:
            colors = ['#00ff88' if c >= o else '#ff4b4b' for c, o in zip(df['Close'], df['Open'])]
        else:
            colors = '#444'
        fig.add_trace(go.Bar(x=str_index, y=df['Volume'], marker_color=colors, name="Volume", showlegend=False), row=2, col=1)

    # 3. Layout generale
    fig.update_layout(
        template="plotly_dark", 
        height=450, 
        margin=dict(l=0, r=45, t=15, b=0), # Margine a destra
        paper_bgcolor='rgba(0,0,0,0)', 
        plot_bgcolor='rgba(0,0,0,0)', 
        xaxis_rangeslider_visible=False,
        hovermode='x unified',
        dragmode='pan'
    )
    
    # 4. Assi e Rimozione Orari di Chiusura (ordine forzato per evitare bug visivi)
    fig.update_xaxes(
        type='category', categoryorder='array', categoryarray=str_index, nticks=10,
        showgrid=True, gridwidth=1, gridcolor='#2a2e39', 
        showspikes=True, spikemode="across", spikesnap="cursor", spikecolor="#888", spikethickness=1
    )
                     
    fig.update_yaxes(side='right', showgrid=True, gridwidth=1, gridcolor='#2a2e39', 
                     showspikes=True, spikemode="across", spikesnap="cursor", spikecolor="#888", spikethickness=1)
    
    return fig

# --- FUNZIONE SENTIMENT POLITICO-ECONOMICO ---
@st.cache_data(ttl=300) 
def analyze_political_economic_news(ticker_full):
    try:
        query = ticker_full.split(" - ")[0].strip()
        url = f"https://news.google.com/rss/search?q={query}+economia+politica+mercati&hl=it&gl=IT"
        res = requests.get(url, timeout=3)
        entries = feedparser.parse(res.content).entries[:15]
        
        if not entries:
            return 0, "Nessuna notizia politica o economica di rilievo nelle ultime ore."
            
        pos_words = ['rialzo', 'crescita', 'accordo', 'positivo', 'taglio tassi', 'stimoli', 'fiducia', 'boom', 'ripresa', 'approvazione', 'supporto', 'investimento', 'sviluppo']
        neg_words = ['crollo', 'crisi', 'inflazione', 'tassi', 'guerra', 'sanzioni', 'dimissioni', 'tensione', 'deficit', 'debito', 'recessione', 'rischio', 'tasse', 'peggiora']
        
        score = 0
        for news in entries:
            title_lower = news.title.lower()
            if any(w in title_lower for w in pos_words): score += 2
            if any(w in title_lower for w in neg_words): score -= 2
                
        return score, f"Analizzate {len(entries)} notizie politico-economiche recenti."
    except:
        return 0, "Errore di connessione ai feed istituzionali."

# --- MOTORE QUANTISTICO BASATO SULLE NOTIZIE ---
class QuantumFinanceEngine:
    @staticmethod
    def get_indicators(df):
        if len(df) > 14:
            delta = df['Close'].diff()
            gain = delta.where(delta > 0, 0.0).ewm(alpha=1/14, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1/14, adjust=False).mean()
            df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-10))))
        else:
            df['RSI'] = 50
        return df.bfill()

    @classmethod
    def calculate_strategy(cls, ticker_full, mode='short'):
        score, reason_base = analyze_political_economic_news(ticker_full)
        
        if mode == 'short':
            if score >= 4: res = {"sig": "COMPRA FORTE", "class": "buy-signal", "reason": f"Clima politico ed economico molto favorevole. {reason_base}"}
            elif score > 0: res = {"sig": "COMPRA", "class": "buy-signal", "reason": f"Decisioni o dati macroeconomici moderatamente positivi. {reason_base}"}
            elif score <= -4: res = {"sig": "VENDI FORTE", "class": "sell-signal", "reason": f"Allerta: forti tensioni geopolitiche o crisi economica. {reason_base}"}
            elif score < 0: res = {"sig": "VENDI", "class": "sell-signal", "reason": f"Incertezza economica o venti contrari governativi. {reason_base}"}
            else: res = {"sig": "ATTENDI", "class": "hold-signal", "reason": f"Situazione macroeconomica in stallo o neutrale. {reason_base}"}
            conf = min(99.0, 50 + abs(score)*8)
        else:
            if score >= 2: res = {"sig": "BULLISH", "class": "buy-signal", "reason": f"Prospettive macroeconomiche di base stabili e costruttive. {reason_base}"}
            elif score <= -2: res = {"sig": "BEARISH", "class": "sell-signal", "reason": f"Rischi sistemici e turbolenze macroeconomiche in vista. {reason_base}"}
            else: res = {"sig": "NEUTRALE", "class": "hold-signal", "reason": f"Il quadro macro è incerto, mancano catalizzatori istituzionali. {reason_base}"}
            conf = min(99.0, 40 + abs(score)*5)
            
        res.update({"conf": conf})
        return res

# --- UI PRINCIPALE ---
st.title("🏛️ Quantum Algorithmic Trader Pro")
tab_trading, tab_conto, tab_news = st.tabs(["📈 Terminale Trading", "💰 Gestione Portafoglio", "📰 Radar Notizie"])

# ==========================================
# PARTE 1: TERMINALE TRADING
# ==========================================
with tab_trading:
    st.markdown("<div class='search-container'>", unsafe_allow_html=True)
    st.markdown("#### 🔍 Selezione Asset")
    
    col_s1, col_s2 = st.columns([3, 2])
    with col_s1:
        search_query = st.text_input("Cerca Azione, Crypto o ETF...", value="", key="main_search", placeholder="es. Tesla, Apple, Bitcoin...")
    
    with col_s2:
        res_sug = search_yahoo_finance(search_query) if search_query else [st.session_state.active_ticker]
        def change_ticker(): st.cache_data.clear()
        
        ticker_sel = st.selectbox("Seleziona:", res_sug, key="ticker_box", on_change=change_ticker)
        if ticker_sel: st.session_state.active_ticker = ticker_sel

    st.markdown("</div>", unsafe_allow_html=True)

    curr_ticker_full = st.session_state.active_ticker
    curr_ticker_id = curr_ticker_full.split(" - ")[0].strip()
    
    col_p1, col_p2 = st.columns(2)
    with col_p1: timeframe = st.radio("Intervallo:", ["1D", "1M", "MAX"], horizontal=True, key="tf_radio")
    with col_p2: chart_ind = st.selectbox("Visualizza:", ["Nessuno", "RSI", "Volumi"], key="ind_box")

    st.divider()

    def render_live_dashboard():
        try:
            p_live, prev_close = get_true_realtime_data(curr_ticker_full)
            df_chart = get_chart_data(curr_ticker_full, timeframe)
            
            if p_live == 0 and not df_chart.empty:
                p_live = df_chart['Close'].iloc[-1]
                prev_close = df_chart['Close'].iloc[0]

            price_formatted = format_price(p_live)
            
            # Gestione Ordini Automatica
            if p_live > 0.0:
                for o in st.session_state.pending_orders:
                    if o['ticker'] == curr_ticker_id:
                        trigger = False
                        if o['type'] == 'TAKE_PROFIT' and p_live >= o['target_price']: trigger = True
                        elif o['type'] == 'STOP_LOSS' and p_live <= o['target_price']: trigger = True
                        if trigger:
                            if curr_ticker_id in st.session_state.portfolio:
                                q_exec = min(o['qty'], st.session_state.portfolio[curr_ticker_id]['qty'])
                                profit = (p_live - st.session_state.portfolio[curr_ticker_id]['avg_price']) * q_exec
                                st.session_state.monthly_pnl += profit
                                st.session_state.balance += (q_exec * p_live)
                                st.session_state.portfolio[curr_ticker_id]['qty'] -= q_exec
                                if st.session_state.portfolio[curr_ticker_id]['qty'] < 0.00001: 
                                    del st.session_state.portfolio[curr_ticker_id]
                                save_transaction_to_db(curr_ticker_id)
                            remove_pending_order(o['id'])
                            st.toast(f"✅ ORDINE ESEGUITO: {o['type']} @ {p_live:.4f}")

            if p_live > 0.0:
                diff = p_live - prev_close
                pct = (diff / prev_close) * 100 if prev_close else 0.0
                c_price = "#00ff88" if diff >= 0 else "#ff4b4b"
                
                c1, c2 = st.columns([3, 1.2])
                with c1:
                    st.markdown(f"""
                        <div style="margin-bottom: 15px;">
                            <span style="font-size: 1.4rem; color: #888;">{curr_ticker_full}</span><br>
                            <span class="live-price-glow" style="text-shadow: 0 0 20px {c_price}80;">{price_formatted} $</span>
                            <span style="color: {c_price}; font-size: 1.3rem; font-weight: bold; margin-left: 20px;">
                                {"+" if diff >= 0 else ""}{diff:.4f} ({"+" if diff >= 0 else ""}{pct:.2f}%)
                            </span>
                        </div>
                    """, unsafe_allow_html=True)

                    if not df_chart.empty:
                        df_ready = QuantumFinanceEngine.get_indicators(df_chart.copy())
                        
                        # ---> GRAFICO A RETTE PROPORZIONATO E BICOLORE <---
                        fig = create_dynamic_chart(df_ready, chart_ind)
                        # Abilitiamo lo scrollZoom per interagire col mouse
                        st.plotly_chart(fig, use_container_width=True, key=f"c_{curr_ticker_id}", config={'scrollZoom': True, 'displayModeBar': False})

                with c2:
                    st.markdown("<div style='background: #1c212c; padding: 15px; border-radius: 15px; border: 1px solid #30363d;'>", unsafe_allow_html=True)
                    st.markdown("<h5 style='margin-top:0;'>🛒 Esegui Ordine</h5>", unsafe_allow_html=True)
                    
                    if curr_ticker_id in st.session_state.portfolio:
                        p_info = st.session_state.portfolio[curr_ticker_id]
                        l_pnl = (p_live - p_info['avg_price']) * p_info['qty']
                        pnl_c = "#00ff88" if l_pnl >= 0 else "#ff4b4b"
                        st.markdown(f"""<div class='live-pnl-box'><span style='color:#888; font-size:0.8rem;'>In Portafoglio: <b>{p_info['qty']:.4f}</b></span><br>
                        <span style='font-size:1rem;'>P/L Live: <b style='color:{pnl_c};'>{l_pnl:+.2f} $</b></span></div>""", unsafe_allow_html=True)

                    inv_val = st.number_input("Importo Ordine ($)", min_value=1.0, value=100.0, step=50.0, key="val_input")
                    calc_qty = inv_val / p_live
                    st.caption(f"Volume stimato: **{calc_qty:.6f}** unità")
                    
                    with st.expander("🛡️ Protezioni"):
                        tp_val = st.number_input("Take Profit ($)", min_value=0.0, value=0.0, step=0.1)
                        sl_val = st.number_input("Stop Loss ($)", min_value=0.0, value=0.0, step=0.1)
                    
                    cb, cs = st.columns(2)
                    with cb:
                        if st.button("📈 BUY", use_container_width=True, type="primary"):
                            if st.session_state.balance >= inv_val:
                                st.session_state.balance -= inv_val
                                port = st.session_state.portfolio
                                if curr_ticker_id in port:
                                    oq, op = port[curr_ticker_id]['qty'], port[curr_ticker_id]['avg_price']
                                    port[curr_ticker_id] = {'qty': oq + calc_qty, 'avg_price': ((oq*op) + inv_val) / (oq+calc_qty)}
                                else:
                                    port[curr_ticker_id] = {'qty': calc_qty, 'avg_price': p_live}
                                save_transaction_to_db(curr_ticker_id)
                                if tp_val > 0: add_pending_order(curr_ticker_id, 'TAKE_PROFIT', tp_val, calc_qty)
                                if sl_val > 0: add_pending_order(curr_ticker_id, 'STOP_LOSS', sl_val, calc_qty)
                                st.rerun()
                            else: st.error("Liquidità insufficiente")
                    with cs:
                        if st.button("📉 SELL", use_container_width=True):
                            port = st.session_state.portfolio
                            if curr_ticker_id in port and port[curr_ticker_id]['qty'] > 0:
                                q_sell = min(calc_qty, port[curr_ticker_id]['qty'])
                                profit = (p_live - port[curr_ticker_id]['avg_price']) * q_sell
                                st.session_state.monthly_pnl += profit
                                st.session_state.balance += (q_sell * p_live)
                                port[curr_ticker_id]['qty'] -= q_sell
                                if port[curr_ticker_id]['qty'] < 0.00001: del port[curr_ticker_id]
                                save_transaction_to_db(curr_ticker_id)
                                st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
                
                # ANALISI POLITICO-ECONOMICA
                st.divider()
                st.markdown("### 🧠 Quantum Insight Engine (Analisi Politico-Economica)")
                if p_live > 0:
                    s_str = QuantumFinanceEngine.calculate_strategy(curr_ticker_full, 'short')
                    l_str = QuantumFinanceEngine.calculate_strategy(curr_ticker_full, 'long')
                    c_an1, c_an2 = st.columns(2)
                    with c_an1:
                        st.markdown(f"""<div class="quantum-card"><h4 style="color:#00e5ff; margin-top:0;">⚡ IMPATTO A BREVE TERMINE</h4>
                            <div class="{s_str['class']}">{s_str['sig']}</div><br>
                            <span style="color:#a3a8b0;">Affidabilità Notizie: {s_str['conf']:.1f}%</span><br>
                            <div class="reasoning-text">{s_str['reason']}</div></div>""", unsafe_allow_html=True)
                    with c_an2:
                        st.markdown(f"""<div class="quantum-card"><h4 style="color:#ff00e5; margin-top:0;">🏛️ SCENARIO LUNGO TERMINE</h4>
                            <div class="{l_str['class']}">{l_str['sig']}</div><br>
                            <span style="color:#a3a8b0;">Affidabilità Notizie: {l_str['conf']:.1f}%</span><br>
                            <div class="reasoning-text">{l_str['reason']}</div></div>""", unsafe_allow_html=True)
            else:
                st.warning("In attesa di dati live... mercato chiuso o ticker non trovato.")
        except Exception as e:
            st.error(f"Errore: {e}")

    # Fragment per aggiornamento automatico
    if hasattr(st, "fragment"):
        @st.fragment(run_every=2.0)
        def main_loop():
            render_live_dashboard()
        main_loop()
    else:
        render_live_dashboard()

# ==========================================
# PARTE 2: IL MIO CONTO
# ==========================================
with tab_conto:
    t_unr = 0.0
    for t, d in st.session_state.portfolio.items():
        lp, _ = get_true_realtime_data(t)
        if lp > 0: t_unr += (lp - d['avg_price']) * d['qty']
    
    eq_tot = st.session_state.balance + t_unr + sum(v['qty']*v['avg_price'] for v in st.session_state.portfolio.values())
    
    ca, cb, cc = st.columns(3)
    ca.metric("Disponibilità Cash", f"{st.session_state.balance:,.2f} $")
    cb.metric("P/L Realizzato (Mese)", f"{st.session_state.monthly_pnl:,.2f} $", delta=f"{st.session_state.monthly_pnl:.2f}")
    cc.metric("Patrimonio Totale", f"{eq_tot:,.2f} $")
    
    st.write("")
    st.markdown("### 💼 Asset in Portafoglio")
    if st.session_state.portfolio:
        for t, d in st.session_state.portfolio.items():
            lp, _ = get_true_realtime_data(t)
            if lp == 0: lp = d['avg_price']
            g = (lp - d['avg_price']) * d['qty']
            gc = "#00ff88" if g >= 0 else "#ff4b4b"
            st.markdown(f"""<div style="background: rgba(255,255,255,0.03); border-left: 5px solid {gc}; padding: 15px; margin-bottom: 10px; border-radius: 8px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <b style="color:#00e5ff; font-size:1.3rem;">{t}</b>
                    <b style="color:{gc}; font-size:1.2rem;">P/L: {g:+.4f} $</b>
                </div>
                <div style="font-size:0.9rem; color:#888;">Quantità: {d['qty']:.6f} | Prezzo Carico: {d['avg_price']:.4f}$ | Valore Attuale: {lp:.4f}$</div>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("Il tuo portafoglio è vuoto.")

# ==========================================
# PARTE 3: RADAR NOTIZIE
# ==========================================
with tab_news:
    @st.cache_data(ttl=600)
    def get_market_news():
        try:
            url = "https://news.google.com/rss/search?q=finanza+mercati+azioni+crypto&hl=it&gl=IT&ceid=IT:it"
            return feedparser.parse(requests.get(url, timeout=5).content).entries[:9]
        except: return []

    all_news = get_market_news()
    if all_news:
        n_cols = st.columns(3)
        for idx, n in enumerate(all_news):
            with n_cols[idx % 3]:
                seed = sum(ord(c) for c in n.title) % 100
                st.markdown(f"""<a href="{n.link}" target="_blank" class="news-link">
                    <div class="news-card">
                        <img src="https://picsum.photos/seed/{seed}/400/200" class="news-img">
                        <div class="news-content">
                            <span style="font-size:0.65rem; color:#00e5ff; border:1px solid #00e5ff; padding:2px 5px; border-radius:4px;">MARKET</span>
                            <div style="padding-top:10px; color:white; font-size:0.95rem; font-weight:bold;">{n.title[:80]}...</div>
                        </div>
                    </div></a>""", unsafe_allow_html=True)

if not hasattr(st, "fragment"):
    time.sleep(2)
    st.rerun()