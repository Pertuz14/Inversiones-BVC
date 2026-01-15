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

# Estilos CSS
st.markdown("""
<style>
    .metric-card {background-color: #f0f2f6; border-radius: 10px; padding: 15px;}
    div[data-testid="stMetricValue"] {font-size: 26px;}
</style>
""", unsafe_allow_html=True)

# --- CONEXIÓN GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- ROBOT BCV ---
@st.cache_data(ttl=3600)
def obtener_tasa_bcv_hoy():
    try:
        r = requests.get("https://www.bcv.org.ve/", verify=False, timeout=5)
        soup = BeautifulSoup(r.content, "html.parser")
        return float(soup.find("div", {"id": "dolar"}).find("strong").text.strip().replace(',', '.'))
    except:
        return 0.0

# --- FUNCIONES DE MEMORIA (BITÁCORA) ---
def actualizar_bitacora_tasas(tasa_actual):
    if tasa_actual <= 0: return 
    try:
        try:
            df_hist = conn.read(worksheet="Historial_Tasas", ttl=0)
            df_hist["Fecha"] = pd.to_datetime(df_hist["Fecha"])
        except:
            df_hist = pd.DataFrame(columns=["Fecha", "Tasa"])
        
        hoy = datetime.now().date()
        fechas_registradas = df_hist["Fecha"].dt.date.tolist() if not df_hist.empty else []
        
        if hoy not in fechas_registradas:
            nuevo = pd.DataFrame([{"Fecha": pd.to_datetime(hoy), "Tasa": tasa_actual}])
            df_up = pd.concat([df_hist, nuevo], ignore_index=True)
            df_up["Fecha"] = df_up["Fecha"].dt.strftime('%Y-%m-%d')
            conn.update(worksheet="Historial_Tasas", data=df_up)
    except:
        pass # Fallo silencioso para no interrumpir al usuario

def buscar_tasa_en_bitacora(fecha_buscada):
    try:
        df_hist = conn.read(worksheet="Historial_Tasas", ttl=600)
        df_hist["Fecha"] = pd.to_datetime(df_hist["Fecha"]).dt.date
        fila = df_hist[df_hist["Fecha"] == fecha_buscada]
        if not fila.empty: return float(fila.iloc[0]["Tasa"])
    except: pass
    return None

# --- FUNCIONES DE DATOS (CON CORRECCIÓN DE ERRORES) ---
def cargar_datos():
    try:
        df = conn.read(worksheet="Portafolio_INTL", ttl=0)
        df["Fecha"] = pd.to_datetime(df["Fecha"])
        return df
    except:
        # Si falla, devolvemos estructura vacía para que no se rompa
        return pd.DataFrame(columns=["Ticker", "Cantidad", "Precio", "Fecha", "Tipo", "Tasa"])

def guardar_operacion(ticker, cantidad, precio, fecha, tipo, tasa_historica):
    try:
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
        
        # Concatenación robusta
        if df_actual.empty:
            df_updated = nuevo
        else:
            # Aseguramos que df_actual tenga la columna Tasa para evitar errores
            if "Tasa" not in df_actual.columns:
                df_actual["Tasa"] = 0.0
            df_updated = pd.concat([df_actual, nuevo], ignore_index=True)
        
        # Formato de fecha estricto para Google Sheets
        df_updated["Fecha"] = df_updated["Fecha"].dt.strftime('%Y-%m-%d')
        
        # INTENTO DE GUARDADO
        conn.update(worksheet="Portafolio_INTL", data=df_updated)
        st.cache_data.clear() # Limpiar memoria para ver cambios
        return True, "Éxito"
        
    except Exception as e:
        return False, str(e)

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

# 1. Tasa de Hoy y Bitácora
tasa_hoy = obtener_tasa_bcv_hoy()
if tasa_hoy == 0:
    tasa_hoy = st.number_input("⚠️ BCV Offline. Tasa Manual:", value=60.0)

actualizar_bitacora_tasas(tasa_hoy)
df_portafolio = cargar_datos()

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("📝 Nueva Operación")
    
    st.write("📅 **Fecha de la Operación**")
    fecha_in = st.date_input("Selecciona fecha:", datetime.now(), label_visibility="collapsed")
    
    # Lógica inteligente de Tasa
    tasa_guardada = buscar_tasa_en_bitacora(fecha_in)
    
    if tasa_guardada:
        val_defecto = tasa_guardada
        msg = "✅ Tasa recuperada del historial."
    elif fecha_in == datetime.now().date():
        val_defecto = tasa_hoy
        msg = "✅ Tasa de HOY."
    else:
        val_defecto = tasa_hoy
        msg = "⚠️ Sin historial. Usa la de hoy o ajusta."

    with st.form("entry_form"):
        st.write("---")
        tipo = st.radio("Acción:", ["Compra", "Venta"], horizontal=True)
        ticker_in = st.text_input("Ticker (Ej: AAPL):").upper().strip()
        
        saldo = 0
        if not df_portafolio.empty and "Ticker" in df_portafolio.columns and ticker_in in df_portafolio["Ticker"].values:
            saldo = df_portafolio[df_portafolio["Ticker"] == ticker_in]["Cantidad"].sum()
        if tipo == "Venta": st.caption(f"Disponible: {saldo}")
        
        cant_in = st.number_input("Cantidad", min_value=0.0001, format="%.4f")
        prec_in = st.number_input("Precio ($)", min_value=0.01, format="%.2f")
        tasa_in = st.number_input("Tasa (Bs/$)", min_value=0.1, value=float(val_defecto), format="%.2f", help=msg)
        
        submitted = st.form_submit_button("Guardar Operación")
        
        if submitted:
            if not ticker_in:
                st.warning("Falta el Ticker.")
            elif tipo == "Venta" and cant_in > saldo:
                st.error("Fondos insuficientes.")
            else:
                # AQUI ESTA LA CORRECCION VISUAL
                with st.spinner("Guardando en Google Sheets..."):
                    exito, mensaje = guardar_operacion(ticker_in, cant_in, prec_in, fecha_in, tipo, tasa_in)
                
                if exito:
                    st.success("¡Guardado correctamente!")
                    st.rerun()
                else:
                    st.error(f"❌ Error crítico: {mensaje}")
                    st.info("Revisa que hayas compartido la hoja con el correo del robot (client_email) y que seas Editor.")

# --- DATOS Y DASHBOARD ---
if not df_portafolio.empty:
    if "Tasa" not in df_portafolio.columns:
        df_portafolio["Tasa"] = tasa_hoy 
    
    df_portafolio["Costo Total $"] = df_portafolio["Cantidad"] * df_portafolio["Precio"]
    df_portafolio["Costo Total Bs"] = df_portafolio["Costo Total $"] * df_portafolio["Tasa"]
    
    df_agrupado = df_portafolio.groupby("Ticker").agg({
        "Cantidad": "sum", "Costo Total $": "sum", "Costo Total Bs": "sum"
    }).reset_index()
    
    df_final = df_agrupado[df_agrupado["Cantidad"] > 0.00001].copy()
    
    precios_live = obtener_precios_actuales(df_final["Ticker"].tolist())
    
    df_final["Precio Actual $"] = df_final["Ticker"].map(precios_live).fillna(0)
    df_final["Valor Hoy $"] = df_final["Cantidad"] * df_final["Precio Actual $"]
    df_final["Valor Hoy Bs"] = df_final["Valor Hoy $"] * tasa_hoy
    df_final["Ganancia $"] = df_final["Valor Hoy $"] - df_final["Costo Total $"]
    df_final["Ganancia Bs"] = df_final["Valor Hoy Bs"] - df_final["Costo Total Bs"]

    # TABS
    t1, t2, t3 = st.tabs(["📊 Portafolio", "🔍 Buscador", "📅 Reportes"])

    with t1:
        c1, c2 = st.columns(2)
        c1.metric("Total ($)", f"${df_final['Valor Hoy $'].sum():,.2f}", delta=f"${df_final['Ganancia $'].sum():,.2f}")
        c2.metric("Total (Bs)", f"Bs.{df_final['Valor Hoy Bs'].sum():,.2f}", delta=f"Bs.{df_final['Ganancia Bs'].sum():,.2f}")
        st.dataframe(df_final, use_container_width=True)

    with t2:
        col_s, col_p = st.columns([3, 1])
        with col_s: search = st.text_input("🔍 Buscar:", key="search_box").upper()
        with col_p: per = st.selectbox("Rango:", ["1mo", "6mo", "1y", "5y"], index=2)
        if search:
            hist = yf.Ticker(search).history(period=per)
            if not hist.empty:
                curr = hist["Close"].iloc[-1]
                st.metric(f"{search}", f"${curr:,.2f}", f"Bs.{curr*tasa_hoy:,.2f}")
                st.line_chart(hist["Close"])
            else: st.warning("No encontrado.")

    with t3:
        filtro = st.selectbox("Periodo:", ["Todo", "Última Semana", "Este Año"])
        df_rep = df_portafolio.copy()
        if filtro == "Última Semana": df_rep = df_rep[df_rep["Fecha"] >= datetime.now() - timedelta(days=7)]
        elif filtro == "Este Año": df_rep = df_rep[df_rep["Fecha"] >= datetime(datetime.now().year, 1, 1)]
        st.dataframe(df_rep.sort_values("Fecha", ascending=False), use_container_width=True)

else:
    st.info("👈 Registra tu primera operación.")
