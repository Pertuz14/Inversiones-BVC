import streamlit as st
import pandas as pd
import plotly.express as px
import yfinance as yf
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Wall St. Pro", page_icon="🇺🇸", layout="wide")

st.markdown("""
<style>
    .metric-card {background-color: #f0f2f6; border-radius: 10px; padding: 15px;}
    div[data-testid="stMetricValue"] {font-size: 26px;}
</style>
""", unsafe_allow_html=True)

# --- CONEXIÓN GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- ROBOT BCV (Para la conversión a Bolívares) ---
@st.cache_data(ttl=3600)
def obtener_tasa_bcv():
    try:
        r = requests.get("https://www.bcv.org.ve/", verify=False, timeout=5)
        soup = BeautifulSoup(r.content, "html.parser")
        return float(soup.find("div", {"id": "dolar"}).find("strong").text.strip().replace(',', '.'))
    except:
        return 0.0

# --- FUNCIONES DE DATOS ---
def cargar_datos():
    try:
        df = conn.read(worksheet="Portafolio_INTL", ttl=0)
        df["Fecha"] = pd.to_datetime(df["Fecha"])
        return df
    except:
        return pd.DataFrame(columns=["Ticker", "Cantidad", "Precio", "Fecha", "Tipo"])

def guardar_operacion(ticker, cantidad, precio, fecha, tipo):
    try:
        df_act = cargar_datos()
        qty = cantidad if tipo == "Compra" else -cantidad
        nuevo = pd.DataFrame([{"Ticker": ticker.upper(), "Cantidad": qty, "Precio": precio, "Fecha": pd.to_datetime(fecha), "Tipo": tipo}])
        
        df_fin = nuevo if df_act.empty else pd.concat([df_act, nuevo], ignore_index=True)
        df_fin["Fecha"] = df_fin["Fecha"].dt.strftime('%Y-%m-%d')
        
        conn.update(worksheet="Portafolio_INTL", data=df_fin)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error guardando: {e}")
        return False

def obtener_precio_live(ticker):
    """Busca precio de UNA sola acción (para el buscador)."""
    try:
        ticker = ticker.upper()
        # Intentamos obtener historial breve
        data = yf.Ticker(ticker).history(period="1d")
        if not data.empty:
            return data["Close"].iloc[-1]
        return 0.0
    except:
        return 0.0

def obtener_precios_masivos(lista_tickers):
    """Busca precios de MUCHAS acciones a la vez (para el portafolio)."""
    if not lista_tickers: return {}
    try:
        # Descarga optimizada
        datos = yf.download(lista_tickers, period="1d", progress=False)['Close']
        precios = {}
        
        if len(lista_tickers) == 1:
            val = datos.iloc[-1]
            precios[lista_tickers[0]] = float(val)
        else:
            current = datos.iloc[-1]
            for t in lista_tickers:
                if t in current: precios[t] = float(current[t])
        return precios
    except:
        return {}

# --- INTERFAZ ---
st.title("🌎 Mi Portafolio Internacional")
st.markdown("---")

# 1. Obtener Tasa BCV
tasa_bcv = obtener_tasa_bcv()
if tasa_bcv == 0: tasa_bcv = st.number_input("⚠️ BCV Offline. Tasa manual:", value=60.0)
else: st.toast(f"Tasa BCV cargada: {tasa_bcv} Bs/$", icon="🇻🇪")

df_raw = cargar_datos()

# --- BARRA LATERAL (REGISTRO) ---
with st.sidebar:
    st.header("📝 Operaciones")
    tipo = st.radio("Tipo", ["Compra", "Venta"], horizontal=True)
    with st.form("op_form"):
        tick_in = st.text_input("Ticker (Ej: AAPL, VOO)").upper()
        
        # Mostrar saldo disponible
        saldo = 0
        if not df_raw.empty and tick_in in df_raw["Ticker"].values:
            saldo = df_raw[df_raw["Ticker"] == tick_in]["Cantidad"].sum()
        if tipo == "Venta": st.caption(f"Disponible: {saldo:.4f}")
        
        cant_in = st.number_input("Cantidad", min_value=0.0001, format="%.4f")
        prec_in = st.number_input("Precio ($)", min_value=0.01, format="%.2f")
        fecha_in = st.date_input("Fecha", datetime.now())
        
        if st.form_submit_button("Guardar"):
            if tipo == "Venta" and cant_in > saldo:
                st.error("Fondos insuficientes.")
            else:
                if guardar_operacion(tick_in, cant_in, prec_in, fecha_in, tipo):
                    st.success("Guardado!")
                    st.rerun()

# --- LÓGICA DE DATOS ---
if not df_raw.empty:
    # Agrupar por Ticker (Consolidado)
    df_resumen = df_raw.groupby("Ticker").agg({"Cantidad": "sum"}).reset_index()
    df_resumen = df_resumen[df_resumen["Cantidad"] > 0.00001] # Filtrar vendidos
    
    # Calcular Costo Promedio Ponderado (Aproximación por costo total)
    df_raw["Costo"] = df_raw["Cantidad"] * df_raw["Precio"]
    costos = df_raw.groupby("Ticker")["Costo"].sum().reset_index()
    df_final = df_resumen.merge(costos, on="Ticker")
    
    # Obtener Precios Actuales
    mis_tickers = df_final["Ticker"].tolist()
    precios_live = obtener_precios_masivos(mis_tickers)
    
    # Cálculos Finales
    df_final["Precio Actual ($)"] = df_final["Ticker"].map(precios_live).fillna(0)
    df_final["Valor Hoy ($)"] = df_final["Cantidad"] * df_final["Precio Actual ($)"]
    df_final["Ganancia ($)"] = df_final["Valor Hoy ($)"] - df_final["Costo"]
    
    # Conversión a Bolívares
    df_final["Precio Actual (Bs)"] = df_final["Precio Actual ($)"] * tasa_bcv
    df_final["Valor Hoy (Bs)"] = df_final["Valor Hoy ($)"] * tasa_bcv
    df_final["Ganancia (Bs)"] = df_final["Ganancia ($)"] * tasa_bcv
    
    df_final["Rentabilidad %"] = (df_final["Ganancia ($)"] / df_final["Costo"]) * 100

    # --- PESTAÑAS PRINCIPALES ---
    tab_dash, tab_search, tab_report = st.tabs(["📊 Mi Portafolio", "🔍 Buscador de Mercado", "📅 Reportes"])

    # ----------------------------------------
    # TAB 1: PORTAFOLIO (MIS ACCIONES)
    # ----------------------------------------
    with tab_dash:
        # KPIs Globales
        tot_usd = df_final["Valor Hoy ($)"].sum()
        gan_usd = df_final["Ganancia ($)"].sum()
        
        tot_bs = tot_usd * tasa_bcv
        gan_bs = gan_usd * tasa_bcv
        
        st.markdown("### 🏦 Resumen Patrimonial")
        
        # Fila Dólares
        c1, c2, c3 = st.columns(3)
        c1.metric("Valor Total ($)", f"${tot_usd:,.2f}")
        c2.metric("Ganancia ($)", f"${gan_usd:,.2f}", delta_color="normal")
        c3.metric("Activos", len(df_final))
        
        # Fila Bolívares
        b1, b2, b3 = st.columns(3)
        b1.metric("Valor Total (Bs)", f"Bs. {tot_bs:,.2f}")
        b2.metric("Ganancia (Bs)", f"Bs. {gan_bs:,.2f}", delta_color="normal")
        b3.write("")
        
        st.divider()
        st.subheader("📜 Mis Acciones (Detallado)")
        
        # Tabla formateada
        st.dataframe(df_final.style.format({
            "Cantidad": "{:.4f}",
            "Precio Actual ($)": "${:.2f}",
            "Valor Hoy ($)": "${:.2f}",
            "Ganancia ($)": "${:.2f}",
            "Precio Actual (Bs)": "Bs{:.2f}",
            "Valor Hoy (Bs)": "Bs{:.2f}",
            "Rentabilidad %": "{:.2f}%"
        }), use_container_width=True)

    # ----------------------------------------
    # TAB 2: BUSCADOR (CUALQUIER ACCIÓN)
    # ----------------------------------------
    with tab_search:
        st.subheader("🔎 Consultar Precio de Mercado")
        search_tick = st.text_input("Ingresa el símbolo (Ej: TSLA, AMZN, BTC-USD):").upper()
        
        if search_tick:
            with st.spinner(f"Buscando {search_tick}..."):
                precio = obtener_precio_live(search_tick)
                if precio > 0:
                    precio_bs = precio * tasa_bcv
                    
                    m1, m2 = st.columns(2)
                    m1.metric(f"Precio {search_tick} ($)", f"${precio:,.2f}")
                    m2.metric(f"Precio {search_tick} (Bs)", f"Bs. {precio_bs:,.2f}")
                    
                    # Mini gráfico rápido
                    try:
                        hist = yf.Ticker(search_tick).history(period="1mo")
                        st.line_chart(hist["Close"])
                    except:
                        st.warning("Gráfico no disponible.")
                else:
                    st.error("No se encontró el ticker. Verifica el nombre.")

    # ----------------------------------------
    # TAB 3: REPORTES (SEMANAL / MENSUAL / ANUAL)
    # ----------------------------------------
    with tab_report:
        st.subheader("📅 Historial de Transacciones")
        
        filtro = st.selectbox("Seleccionar Periodo:", ["Todo el Historial", "Última Semana", "Último Mes", "Este Año"])
        
        df_rep = df_raw.copy()
        hoy = datetime.now()
        
        if filtro == "Última Semana":
            fecha_corte = hoy - timedelta(days=7)
            df_rep = df_rep[df_rep["Fecha"] >= fecha_corte]
        elif filtro == "Último Mes":
            fecha_corte = hoy - timedelta(days=30)
            df_rep = df_rep[df_rep["Fecha"] >= fecha_corte]
        elif filtro == "Este Año":
            fecha_corte = datetime(hoy.year, 1, 1)
            df_rep = df_rep[df_rep["Fecha"] >= fecha_corte]
            
        if not df_rep.empty:
            # Métricas del periodo seleccionado
            inv_periodo = df_rep[df_rep["Tipo"]=="Compra"]["Precio"] * df_rep[df_rep["Tipo"]=="Compra"]["Cantidad"]
            total_inv_periodo = inv_periodo.sum()
            
            c1, c2 = st.columns(2)
            c1.metric("Dinero Movido en Periodo ($)", f"${total_inv_periodo:,.2f}")
            c2.metric("Transacciones", len(df_rep))
            
            st.dataframe(df_rep.sort_values("Fecha", ascending=False).style.format({
                "Precio": "${:.2f}",
                "Cantidad": "{:.4f}",
                "Fecha": "{:%Y-%m-%d}"
            }), use_container_width=True)
        else:
            st.info("No hay movimientos en este periodo.")

else:
    st.info("👈 Registra tu primera operación internacional para activar el dashboard.")
