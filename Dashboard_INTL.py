import streamlit as st
import pandas as pd
import plotly.express as px
import yfinance as yf
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Wall St. Portfolio", page_icon="🇺🇸", layout="wide")

# Estilos CSS (Mantenemos tu estilo original)
st.markdown("""
<style>
    .metric-card {background-color: #f0f2f6; border-radius: 10px; padding: 15px;}
    div[data-testid="stMetricValue"] {font-size: 26px;}
</style>
""", unsafe_allow_html=True)

# --- CONEXIÓN GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- ROBOT BCV (Sin cambios) ---
@st.cache_data(ttl=3600)
def obtener_tasa_bcv_hoy():
    try:
        r = requests.get("https://www.bcv.org.ve/", verify=False, timeout=5)
        soup = BeautifulSoup(r.content, "html.parser")
        return float(soup.find("div", {"id": "dolar"}).find("strong").text.strip().replace(',', '.'))
    except:
        return 0.0

# ==========================================
#     ⬇️ AQUÍ ESTÁN LAS NUEVAS FUNCIONES ⬇️
# ==========================================

def actualizar_bitacora_tasas(tasa_actual):
    """Guarda la tasa de HOY en la hoja 'Historial_Tasas'."""
    if tasa_actual <= 0: return 
    try:
        try:
            # Intentamos leer la hoja historial
            df_hist = conn.read(worksheet="Historial_Tasas", ttl=0)
            df_hist["Fecha"] = pd.to_datetime(df_hist["Fecha"])
        except:
            # Si no existe, creamos el dataframe vacío
            df_hist = pd.DataFrame(columns=["Fecha", "Tasa"])
        
        hoy = datetime.now().date()
        # Lista de fechas ya guardadas
        fechas_registradas = df_hist["Fecha"].dt.date.tolist() if not df_hist.empty else []
        
        # Si hoy no está guardado, lo guardamos
        if hoy not in fechas_registradas:
            nuevo = pd.DataFrame([{"Fecha": pd.to_datetime(hoy), "Tasa": tasa_actual}])
            df_up = pd.concat([df_hist, nuevo], ignore_index=True)
            df_up["Fecha"] = df_up["Fecha"].dt.strftime('%Y-%m-%d')
            conn.update(worksheet="Historial_Tasas", data=df_up)
    except Exception as e:
        print(f"Error bitácora: {e}")

def buscar_tasa_en_bitacora(fecha_buscada):
    """Busca si tenemos guardada la tasa de una fecha específica."""
    try:
        df_hist = conn.read(worksheet="Historial_Tasas", ttl=600)
        df_hist["Fecha"] = pd.to_datetime(df_hist["Fecha"]).dt.date
        fila = df_hist[df_hist["Fecha"] == fecha_buscada]
        if not fila.empty: return float(fila.iloc[0]["Tasa"])
    except: pass
    return None

# ==========================================
#     ⬆️ FIN DE NUEVAS FUNCIONES ⬆️
# ==========================================

# --- FUNCIONES DE DATOS (Sin cambios estructurales) ---
def cargar_datos():
    try:
        df = conn.read(worksheet="Portafolio_INTL", ttl=0)
        df["Fecha"] = pd.to_datetime(df["Fecha"])
        return df
    except:
        return pd.DataFrame(columns=["Ticker", "Cantidad", "Precio", "Fecha", "Tipo", "Tasa"])

def guardar_operacion(ticker, cantidad, precio, fecha, tipo, tasa_historica):
    df_actual = cargar_datos()
    
    qty_final = cantidad if tipo == "Compra" else -cantidad
    
    nuevo = pd.DataFrame([{
        "Ticker": ticker.upper(),
        "Cantidad": qty_final,
        "Precio": precio,
        "Fecha": pd.to_datetime(fecha),
        "Tipo": tipo,
        "Tasa": tasa_historica
    }])
    
    if df_actual.empty:
        df_updated = nuevo
    else:
        df_updated = pd.concat([df_actual, nuevo], ignore_index=True)
    
    df_updated["Fecha"] = df_updated["Fecha"].dt.strftime('%Y-%m-%d')
    conn.update(worksheet="Portafolio_INTL", data=df_updated)
    st.cache_data.clear()

def obtener_precios_actuales(lista_tickers):
    if not lista_tickers: return {}
    try:
        datos = yf.download(lista_tickers, period="1d", progress=False)['Close']
        precios = {}
        if len(lista_tickers) == 1:
            val = datos.iloc[-1]
            precios[lista_tickers[0]] = float(val)
        else:
            current = datos.iloc[-1]
            for tick in lista_tickers:
                if tick in current: precios[tick] = float(current[tick])
        return precios
    except:
        return {}

# --- INTERFAZ PRINCIPAL ---
st.title("🌎 Mi Portafolio Internacional")
st.markdown("---")

# 1. Obtener Tasa de Hoy
tasa_hoy = obtener_tasa_bcv_hoy()
if tasa_hoy == 0:
    tasa_hoy = st.number_input("⚠️ BCV Offline. Tasa de HOY manual:", value=60.0)

# >>> INSERCIÓN 1: Guardar tasa de hoy en la memoria <<<
actualizar_bitacora_tasas(tasa_hoy)

df_portafolio = cargar_datos()

# --- BARRA LATERAL (AQUÍ ESTÁ EL CAMBIO CLAVE) ---
with st.sidebar:
    st.header("📝 Nueva Operación")
    
    # >>> CAMBIO: La fecha va FUERA del formulario para ser interactiva <<<
    st.write("📅 **Fecha de la Operación**")
    fecha_in = st.date_input("Selecciona fecha:", datetime.now(), label_visibility="collapsed")
    
    # >>> CAMBIO: Lógica para buscar la tasa automáticamente <<<
    tasa_guardada = buscar_tasa_en_bitacora(fecha_in)
    
    if tasa_guardada:
        valor_defecto = tasa_guardada
        msg_ayuda = "✅ Tasa recuperada de tu historial."
        st.success(f"Día {fecha_in.day}/{fecha_in.month}: {tasa_guardada} Bs/$")
    elif fecha_in == datetime.now().date():
        valor_defecto = tasa_hoy
        msg_ayuda = "✅ Tasa actual del BCV (Hoy)."
    else:
        valor_defecto = tasa_hoy
        msg_ayuda = "⚠️ No hay registro histórico. Usa la de hoy o edítala."
        st.info("Sin datos históricos. Ingresa tasa manual.")

    with st.form("entry_form"):
        st.write("---")
        tipo = st.radio("Acción:", ["Compra", "Venta"], horizontal=True)
        ticker_in = st.text_input("Ticker (Ej: AAPL, BTC-USD)").upper()
        
        saldo = 0
        if not df_portafolio.empty and "Ticker" in df_portafolio.columns and ticker_in in df_portafolio["Ticker"].values:
            saldo = df_portafolio[df_portafolio["Ticker"] == ticker_in]["Cantidad"].sum()
        if tipo == "Venta": st.caption(f"Tienes {saldo} disponibles.")
        
        cant_in = st.number_input("Cantidad", min_value=0.0001, format="%.4f")
        prec_in = st.number_input("Precio ($)", min_value=0.01, format="%.2f")
        
        # >>> CAMBIO: El campo tasa se llena solo con 'valor_defecto' <<<
        tasa_in = st.number_input("Tasa Cambio (Bs/$)", min_value=0.1, value=float(valor_defecto), format="%.2f", help=msg_ayuda)
        
        if st.form_submit_button("Guardar Operación"):
            if not ticker_in:
                st.warning("Escribe un Ticker.")
            elif tipo == "Venta" and cant_in > saldo:
                st.error("No tienes suficientes acciones.")
            else:
                guardar_operacion(ticker_in, cant_in, prec_in, fecha_in, tipo, tasa_in)
                st.success("Guardado!")
                st.rerun()

# --- PROCESAMIENTO DE DATOS (Mantenemos todo igual) ---
if not df_portafolio.empty:
    if "Tasa" not in df_portafolio.columns:
        df_portafolio["Tasa"] = tasa_hoy 
    
    # Costos
    df_portafolio["Costo Total $"] = df_portafolio["Cantidad"] * df_portafolio["Precio"]
    df_portafolio["Costo Total Bs"] = df_portafolio["Costo Total $"] * df_portafolio["Tasa"]
    
    # Agrupar
    df_agrupado = df_portafolio.groupby("Ticker").agg({
        "Cantidad": "sum",
        "Costo Total $": "sum",
        "Costo Total Bs": "sum"
    }).reset_index()
    
    df_final = df_agrupado[df_agrupado["Cantidad"] > 0.00001].copy()
    
    # Precios Live
    lista_tickers = df_final["Ticker"].tolist()
    precios_live = obtener_precios_actuales(lista_tickers)
    
    df_final["Precio Actual $"] = df_final["Ticker"].map(precios_live).fillna(0)
    df_final["Valor Hoy $"] = df_final["Cantidad"] * df_final["Precio Actual $"]
    df_final["Valor Hoy Bs"] = df_final["Valor Hoy $"] * tasa_hoy
    
    df_final["Ganancia $"] = df_final["Valor Hoy $"] - df_final["Costo Total $"]
    df_final["Ganancia Bs"] = df_final["Valor Hoy Bs"] - df_final["Costo Total Bs"]

    # --- TABS (Mantenemos las 3 pestañas originales) ---
    tab1, tab2, tab3 = st.tabs(["📊 Mi Portafolio", "🔍 Buscador Mercado", "📅 Reportes"])

    # TAB 1: PORTAFOLIO
    with tab1:
        st.subheader("Estado Actual")
        c1, c2 = st.columns(2)
        c1.metric("Valor Total ($)", f"${df_final['Valor Hoy $'].sum():,.2f}", delta=f"${df_final['Ganancia $'].sum():,.2f}")
        c2.metric("Valor Total (Bs)", f"Bs. {df_final['Valor Hoy Bs'].sum():,.2f}", delta=f"Bs. {df_final['Ganancia Bs'].sum():,.2f}")
        st.divider()
        st.dataframe(df_final[[
            "Ticker", "Cantidad", "Precio Actual $", "Valor Hoy $", "Ganancia $", "Valor Hoy Bs", "Ganancia Bs"
        ]].style.format({
            "Cantidad": "{:.4f}", "Precio Actual $": "${:.2f}", "Valor Hoy $": "${:.2f}", "Ganancia $": "${:.2f}",
            "Valor Hoy Bs": "Bs.{:,.2f}", "Ganancia Bs": "Bs.{:,.2f}"
        }), use_container_width=True)

    # TAB 2: BUSCADOR CON FILTRO TEMPORAL
    with tab2:
        col_s, col_p = st.columns([3, 1])
        with col_s: search = st.text_input("🔍 Buscar (Ej: NVDA):").upper()
        # Mantenemos el selector que pediste
        with col_p: per = st.selectbox("Rango:", ["1mo", "6mo", "1y", "5y", "10y", "max"], index=2)
        
        if search:
            hist = yf.Ticker(search).history(period=per)
            if not hist.empty:
                curr = hist["Close"].iloc[-1]
                st.metric(f"{search} ($)", f"${curr:,.2f}", f"Bs. {curr*tasa_hoy:,.2f}")
                st.line_chart(hist["Close"])
            else: st.warning("No encontrado.")

    # TAB 3: REPORTES TEMPORALES
    with tab3:
        st.subheader("📜 Historial")
        filtro = st.selectbox("Periodo:", ["Todo", "Última Semana", "Este Año"])
        df_rep = df_portafolio.copy()
        if filtro == "Última Semana": df_rep = df_rep[df_rep["Fecha"] >= datetime.now() - timedelta(days=7)]
        elif filtro == "Este Año": df_rep = df_rep[df_rep["Fecha"] >= datetime(datetime.now().year, 1, 1)]
        
        if not df_rep.empty:
            st.dataframe(df_rep.sort_values("Fecha", ascending=False).style.format({
                "Precio": "${:.2f}", "Tasa": "Bs.{:.2f}", "Costo Total $": "${:.2f}", "Fecha": "{:%Y-%m-%d}"
            }))
        else: st.info("Sin datos.")

else:
    st.info("👈 Registra tu primera operación.")
