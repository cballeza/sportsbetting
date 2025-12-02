import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from openai import OpenAI
import os
import time
import requests
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

# --- CONFIGURATION & ASSETS ---
load_dotenv()
ST_PAGE_TITLE = "SmartBetting"
st.set_page_config(
    page_title=ST_PAGE_TITLE, 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# --- FIREBASE SETUP ---
if not firebase_admin._apps:
    # Ensure you have your service_account.json in the same folder
    cred = credentials.Certificate('service_account.json')
    firebase_admin.initialize_app(cred)

db = firestore.client()
USER_ID = "demo_user_123" 

# --- 🎨 DESIGN SYSTEM (CSS) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap');
    .stApp { background-color: #0e1117; font-family: 'JetBrains Mono', monospace; }
    h1, h2, h3, h4, p, div, span { font-family: 'JetBrains Mono', monospace; letter-spacing: -0.5px; }
    .page-title {
        font-family: 'JetBrains Mono', monospace;
        font-size: 2.8rem;
        font-weight: 700;
        color: #f8fafc;
        margin-bottom: 0.2rem;
        letter-spacing: -1px;
    }
    
    /* GLASS CARDS */
    .glass-card {
        background: rgba(26, 28, 36, 0.6);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    /* ODDS BOXES */
    .odds-box {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 12px;
        text-align: center;
        cursor: default;
    }
    .odds-number {
        color: #10b981;
        font-family: 'JetBrains Mono', monospace;
        font-weight: bold;
        font-size: 1.1rem;
    }
    
    /* SIDEBAR & METRICS */
    section[data-testid="stSidebar"] { background-color: #020617; border-right: 1px solid #1e293b; }
    div[data-testid="stMetricValue"] { color: #f8fafc; font-size: 1.8rem; font-family: 'JetBrains Mono', monospace; }
    .stButton > button { border-radius: 8px; font-weight: 600; border: 1px solid #334155; background-color: #1e293b; color: #f1f5f9; font-family: 'JetBrains Mono', monospace; }
    button[kind="primary"] { background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important; border: none !important; color: #ffffff !important; }
    
    /* AI BOX */
    .ai-box { border-left: 3px solid #6366f1; background: rgba(99, 102, 241, 0.05); padding: 15px; border-radius: 0 8px 8px 0; margin-top: 15px; }
    </style>
""", unsafe_allow_html=True)

# --- BACKEND LOGIC ---
def display_odds(american_odds, format_pref):
    try:
        odds = float(american_odds)
    except:
        return "N/A"
    
    if format_pref == "Decimal":
        if odds > 0:
            decimal = (odds / 100) + 1
        else:
            decimal = (100 / abs(odds)) + 1
        return f"{decimal:.2f}"
    else:
        # American Format
        return f"+{int(odds)}" if odds > 0 else f"{int(odds)}"

def odds_to_prob(american_odds):
    try: odds = float(american_odds)
    except: return 0.5
    if odds > 0: return 100 / (odds + 100)
    else: return (-odds) / (-odds + 100)

def calculate_payout(stake, american_odds):
    try: odds = float(american_odds)
    except: return 0.0
    if odds > 0: profit = stake * (odds / 100)
    else: profit = stake * (100 / abs(odds))
    return profit

# CACHED API CALLS
@st.cache_data(ttl=300) 
def fetch_odds_data(api_key, sport_key):
    if not api_key: return []
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/?regions=us&markets=h2h&oddsFormat=american&apiKey={api_key}"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []

class OddsManager:
    def __init__(self):
        self.api_key = os.getenv("ODDS_API_KEY")

    def get_sports(self):
        sports_list = []
        
        # 1. Add Real Sports if Key Exists
        if self.api_key:
            try:
                url = f"https://api.the-odds-api.com/v4/sports/?apiKey={self.api_key}"
                response = requests.get(url)
                if response.status_code == 200:
                    popular = ['basketball_nba', 'americanfootball_nfl', 'hockey_nhl', 'soccer_epl']
                    data = response.json()
                    sports_list = [s for s in data if s['key'] in popular or s['active']]
            except: pass
            
        # 2. ALWAYS Add Simulation League for Testing
        sports_list.insert(0, {"title": "🛠 Simulation League", "key": "sim_league", "active": True})
        return sports_list

def get_ai_analysis(match_title, team_picked, odds):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key: return "AI Configuration missing."
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    prompt = f"""

    Act as a professional Sports Quantitative Analyst. 
    Conduct a rigorous value analysis for the following wager:
    - Match: {match_title}
    - Selection: {team_picked}
    - Odds: {odds}

    Your report must include:
    1. **Implied Probability**: Explain the implied probability while stating the final percentage. Do not show the formula or calculation steps.
    2. **Contextual Analysis**: Evaluate recent form, head-to-head records, and key situational factors (injuries, motivation, home/away advantage).
    3. **Value Assessment**: Do you believe the true probability of winning is higher than the implied probability? Explain the "Edge".
    4. **Final Verdict**: Classify as 'High Value (Bet)', 'Marginal Value', or 'Negative Expected Value (Avoid)'.
    5. **Risk Management**: Provide a specific bankroll management tip or safety warning based on the volatility of this specific match.
    """
    try:
        response = client.chat.completions.create(model="openai/gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        return response.choices[0].message.content
    except Exception as e: return f"Error: {e}"

# --- STATE MANAGEMENT ---
if 'bankroll' not in st.session_state:
    try:
        doc = db.collection('users').document(USER_ID).get()
        if doc.exists: st.session_state.bankroll = doc.to_dict().get('bankroll', 1000.00)
        else:
            st.session_state.bankroll = 1000.00
            db.collection('users').document(USER_ID).set({'bankroll': 1000.00})
    except: st.session_state.bankroll = 1000.00

# --- SIDEBAR ---
with st.sidebar:
    st.title("Wallet")
    st.markdown(f"""
        <div style="background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%); padding: 20px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 20px;">
            <div style="color: #94a3b8; font-size: 0.9rem;">Total Balance</div>
            <div style="color: #ffffff; font-size: 1.8rem; font-weight: bold; font-family: 'JetBrains Mono';">${st.session_state.bankroll:,.2f}</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    st.markdown("### ⚙️ Settings")
    odds_format = st.radio("Odds Display", ["American", "Decimal"], horizontal=True)
    
    if st.button("Reset Account", use_container_width=True):
        st.session_state.bankroll = 1000.00
        db.collection('users').document(USER_ID).update({'bankroll': 1000.00})
        st.rerun()

    # --- [NEW] SIMULATION TOOLS ---
    st.divider()
    st.markdown("### (Dev)")
    st.caption("Force result of most recent pending bet:")
    
    col_sim1, col_sim2 = st.columns(2)
    
    # Logic to fetch last pending bet
    last_bet_query = db.collection("bets")\
        .where("user_id", "==", USER_ID)\
        .where("result", "==", "PENDING")\
        .order_by("timestamp", direction=firestore.Query.DESCENDING)\
        .limit(1)
    
    last_bet_docs = list(last_bet_query.stream())
    
    if last_bet_docs:
        last_bet_ref = last_bet_docs[0].reference
        last_bet_data = last_bet_docs[0].to_dict()
        payout_amt = last_bet_data.get('potential_payout', 0)
        
        with col_sim1:
            if st.button("Force WIN", type="primary", use_container_width=True):
                # 1. Update Bet Status
                last_bet_ref.update({"result": "WIN"})
                # 2. Credit User
                db.collection('users').document(USER_ID).update({'bankroll': firestore.Increment(payout_amt)})
                st.session_state.bankroll += payout_amt
                st.toast(f"Result Simulated: WIN (+${payout_amt:.2f})", icon="💰")
                time.sleep(1)
                st.rerun()
                
        with col_sim2:
            if st.button("Force LOSS", use_container_width=True):
                # 1. Update Bet Status
                last_bet_ref.update({"result": "LOSS"})
                st.toast("Result Simulated: LOSS", icon="💀")
                time.sleep(1)
                st.rerun()
    else:
        st.caption("No pending bets to simulate.")

# --- MAIN DASHBOARD ---
st.markdown("<h1 class='page-title'>SmartBetting</h1>", unsafe_allow_html=True)
st.markdown("<span style='color: #64748b;'>AI-Powered Odds Research & Risk Management</span>", unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

manager = OddsManager()
col_market, col_ticket = st.columns([2, 1], gap="medium")

# Init variables for global scope
selected_game_data = None
team_options = []
selected_game_title = ""

# --- MARKET FEED COLUMN ---
with col_market:
    st.markdown('<div class="section-header">Market Feed</div>', unsafe_allow_html=True)
    
    games_list = []
    active_sports = manager.get_sports()
    sports_map = {s['title']: s['key'] for s in active_sports}
    selected_sport_name = st.selectbox("Select League", options=list(sports_map.keys()))
    
    if selected_sport_name:
        sport_key = sports_map[selected_sport_name]
        
        # --- [NEW] SIMULATION DATA ---
        if sport_key == "sim_league":
             # Create a dummy game for testing
            games_list.append({
                "id": "sim_game_001",
                "home": "Python Script",
                "away": "The Bug",
                "title": "The Bug @ Python Script",
                "odds": {"Python Script": -150, "The Bug": +130}
            })
            #st.info("Currently in Simulation Mode. Bets placed here do not use real money.")
        # --- REAL DATA ---
        else:
            with st.spinner("Fetching live odds..."):
                raw_games = fetch_odds_data(manager.api_key, sport_key)
                for g in raw_games:
                    bookmakers = g.get('bookmakers', [])
                    if bookmakers:
                        odds_market = bookmakers[0]['markets'][0]['outcomes']
                        odds_dict = {o['name']: o['price'] for o in odds_market}
                        games_list.append({
                            "id": g['id'],
                            "home": g['home_team'],
                            "away": g['away_team'],
                            "title": f"{g['away_team']} @ {g['home_team']}",
                            "odds": odds_dict
                        })

    if games_list:
        game_options = {g['title']: g for g in games_list}
        selected_game_title = st.selectbox("Select Matchup", options=list(game_options.keys()))
        selected_game_data = game_options[selected_game_title]
        
        st.markdown("---")
        
        team_options = list(selected_game_data['odds'].keys())
        oc1, oc2 = st.columns(2)
        
        def render_team_box(col, team_name, odds_val):
            formatted_val = display_odds(odds_val, odds_format)
            with col:
                st.markdown(f"""
                <div class="odds-box">
                    <div style="font-size: 0.9rem; color: #cbd5e1; margin-bottom: 5px;">{team_name}</div>
                    <div class="odds-number">{formatted_val}</div>
                </div>
                """, unsafe_allow_html=True)

        if len(team_options) > 1:
            render_team_box(oc2, f"{team_options[1]}", selected_game_data['odds'].get(team_options[1], 'N/A'))
            render_team_box(oc1, f"{team_options[0]}", selected_game_data['odds'].get(team_options[0], 'N/A'))
    else:
        st.info("Select a league to populate the board.")
    
    if games_list and team_options and selected_game_data:
        st.markdown('<div class="section-header" style="margin-top: 2rem;">AI Value Consultant</div>', unsafe_allow_html=True)
        selected_team_ai = st.selectbox("Team to Analyze", options=team_options, label_visibility="collapsed")
        ai_odds = selected_game_data['odds'].get(selected_team_ai, -110)
        
        if st.button("Run Value Analysis", use_container_width=True):
            with st.spinner("Processing..."):
                analysis = get_ai_analysis(selected_game_title, selected_team_ai, ai_odds)
                st.markdown(f'<div class="ai-box">{analysis}</div>', unsafe_allow_html=True)

# --- BET SLIP COLUMN ---
with col_ticket:
    # ROI Metrics
    start = 1000.00
    current = st.session_state.bankroll
    pnl = current - start
    color_pnl = "#10b981" if pnl >= 0 else "#ef4444"

    st.markdown(f"""
    <div class="glass-card" style="padding: 15px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="text-align: center; flex: 1;">
                <div style="color: #94a3b8; font-size: 0.8rem;">ROI</div>
                <div style="color: {color_pnl}; font-size: 1.1rem; font-weight: bold; font-family: 'JetBrains Mono';">{((current-start)/start)*100:.2f}%</div>
            </div>
            <div style="width: 1px; height: 30px; background: #334155; margin: 0 10px;"></div>
            <div style="text-align: center; flex: 1;">
                <div style="color: #94a3b8; font-size: 0.8rem;">Net PnL</div>
                <div style="color: {color_pnl}; font-size: 1.1rem; font-weight: bold; font-family: 'JetBrains Mono';">${pnl:+,.2f}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-header" style="margin-top: 1.5rem;">Bet Slip</div>', unsafe_allow_html=True)
    
    if games_list and team_options and selected_game_data:
        st.markdown(f"<div style='margin-bottom: 15px; font-weight: bold;'>{selected_game_title}</div>", unsafe_allow_html=True)
        
        # Input Section
        selected_team = st.selectbox("Your Pick", options=team_options)
        current_odds = selected_game_data['odds'].get(selected_team, -110)
        
        stake = st.number_input("Wager ($)", min_value=1.0, value=50.0, step=10.0)
        
        # Calculations
        implied_prob = odds_to_prob(current_odds) * 100
        potential_profit = calculate_payout(stake, current_odds)
        total_payout = stake + potential_profit
        
        st.markdown("---")
        
        # Slip Summary
        row1 = st.columns(2)
        row1[0].caption("Odds")
        row1[0].markdown(f"**{display_odds(current_odds, odds_format)}**")
        row1[1].caption("Imp. Prob")
        row1[1].markdown(f"**{implied_prob:.1f}%**")
        
        row2 = st.columns(2)
        row2[0].caption("To Win")
        row2[0].markdown(f"<span style='color:#10b981'>${potential_profit:.2f}</span>", unsafe_allow_html=True)
        row2[1].caption("Total Payout")
        row2[1].markdown(f"**${total_payout:.2f}**")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # PLACE BET BUTTON
        if st.button(f"CONFIRM BET", type="primary", use_container_width=True):
            if stake > st.session_state.bankroll:
                st.error("Insufficient Funds")
            else:
                # 1. Deduct Funds
                st.session_state.bankroll -= stake
                db.collection('users').document(USER_ID).update({'bankroll': firestore.Increment(-stake)})
                
                # 2. Save Bet to Firestore
                bet_data = {
                    "user_id": USER_ID,
                    "game_id": selected_game_data['id'],
                    "match": selected_game_title,
                    "pick": selected_team,
                    "type": "Moneyline", 
                    "odds": current_odds,
                    "stake": stake,
                    "potential_payout": total_payout,
                    "result": "PENDING",
                    "timestamp": firestore.SERVER_TIMESTAMP
                }
                
                db.collection("bets").add(bet_data)
                
                st.success("Bet Placed & Saved!")
                time.sleep(1)
                st.rerun()

    else:
        st.info("Selection Pending...")
        
# --- HISTORY SECTION ---
st.markdown('<div class="section-header">Transaction History</div>', unsafe_allow_html=True)
try:
    docs = db.collection("bets")\
        .where("user_id", "==", USER_ID)\
        .order_by("timestamp", direction=firestore.Query.DESCENDING)\
        .stream()
    
    history_data = []
    for doc in docs:
        d = doc.to_dict()
        history_data.append({
            "Match": d.get('match'),
            "Pick": d.get('pick'),
            "Stake": d.get('stake', 0),
            "Result": d.get('result', 'PENDING')
        })
    
    if history_data:
        df = pd.DataFrame(history_data)
        def style_dataframe(row):
            color = 'white'
            if row['Result'] == 'WIN': color = '#10b981'
            elif row['Result'] == 'LOSS': color = '#ef4444'
            elif row['Result'] == 'PENDING': color = '#f59e0b'
            return [f'color: {color}; font-weight: bold' if col == 'Result' else '' for col in row.index]

        st.dataframe(
            df.style.apply(style_dataframe, axis=1),
            use_container_width=True,
            hide_index=True,
            column_config={"Stake": st.column_config.NumberColumn(format="$%.2f")}
        )
    else:
        st.info("No betting history found.")
except Exception as e:
    st.warning(f"History unavailable: {e}")