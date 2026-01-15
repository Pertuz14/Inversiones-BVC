import streamlit as st
import pandas as pd
import plotly.express as px
import yfinance as yf
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Wall St. Portfolio", page_icon="🇺🇸", layout="wide")

# Estilos
st.markdown("""
<style>
    .metric-card {background-color: #f0f2f6; border-radius: 10px; padding: 15px;}
    div[data-testid="stMetricValue"] {font-size: 26px;}
</style>
""", unsafe_allow_html=True)

# --- CONEXIÓN GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- ROBOT BCV (Necesario para saber a cuánto está el Bs HOY) ---
@st.cache_data(ttl=3600)
def obtener_tasa_bcv_hoy():
    actualizar_bitacora_tasas(tasa_hoy)
    try:
        r = requests.get("https://www.bcv.org.ve/", verify=False, timeout=5)
        soup = BeautifulSoup(r.content, "html.parser")
        return float(soup.find("div", {"id": "dolar"}).find("strong").text.strip().replace(',', '.'))
    except:
        return 0.0

# --- NUEVAS FUNCIONES: BITÁCORA DE TASAS (MEMORIA) ---
def actualizar_bitacora_tasas(tasa_actual):
    """Guarda la tasa de HOY en la hoja 'Historial_Tasas' si no existe aún."""
    if tasa_actual <= 0: return 
    try:
        try:
            df_hist = conn.read(worksheet="Historial_Tasas", ttl=0)
            df_hist["Fecha"] = pd.to_datetime(df_hist["Fecha"])
        except:
            df_hist = pd.DataFrame(columns=["Fecha", "Tasa"])
        
        hoy = datetime.now().date()
        fechas_registradas = df_hist["Fecha"].dt.date.tolist() if not df_hist.empty else []
        tasa_guardada = buscar_tasa_en_bitacora(fecha_in)
    
    if tasa_guardada:
        valor_defecto = tasa_guardada
        msg = "✅ Tasa recuperada del historial."
    else:
        valor_defecto = tasa_hoy
        msg = "Usando tasa de hoy (ajustar si es necesario)."

    with st.form("entry_form"):
        # ... (Ticker, Cantidad, Precio siguen igual) ...
        
        # MODIFICA EL INPUT DE TASA ASÍ:
        tasa_in = st.number_input("Tasa Cambio (Bs/$)", value=float(valor_defecto), help=msg)
        
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

# --- FUNCIONES DE DATOS ---
def cargar_datos():
    try:
        # Leemos la hoja. Si no existe la columna Tasa, se creará después.
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
        "Tasa": tasa_historica # <--- Guardamos la tasa de ESE día
    }])
    
    # Concatenar asegurando que todas las columnas existan
    if df_actual.empty:
        df_updated = nuevo
    else:
        df_updated = pd.concat([df_actual, nuevo], ignore_index=True)
    
    # Formato fecha seguro para Sheets
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

# --- INTERFAZ ---
st.title("🌎 Mi Portafolio Internacional")
st.markdown("---")

tasa_hoy = obtener_tasa_bcv_hoy()
if tasa_hoy == 0:
    tasa_hoy = st.number_input("⚠️ BCV Offline. Tasa de HOY manual:", value=60.0)

df_portafolio = cargar_datos()

# --- BARRA LATERAL (REGISTRO) ---
with st.sidebar:
    st.header("📝 Nueva Operación")
    tipo = st.radio("Acción:", ["Compra", "Venta"], horizontal=True)
    
    with st.form("entry_form"):
        ticker_in = st.text_input("Ticker (Ej: AAPL, BTC-USD)").upper()
        
        saldo = 0
        if not df_portafolio.empty and "Ticker" in df_portafolio.columns and ticker_in in df_portafolio["Ticker"].values:
            saldo = df_portafolio[df_portafolio["Ticker"] == ticker_in]["Cantidad"].sum()
        if tipo == "Venta": st.caption(f"Tienes {saldo} disponibles.")
        
        cant_in = st.number_input("Cantidad", min_value=0.0001, format="%.4f")
        prec_in = st.number_input("Precio ($)", min_value=0.01, format="%.2f")
        fecha_in = st.date_input("Fecha", datetime.now())
        
        # --- AQUÍ ESTÁ LO QUE PEDISTE ---
        st.markdown("---")
        st.write("🇻🇪 **Datos de Cambio**")
        st.caption("Indica la tasa del BCV del día de la operación:")
        tasa_in = st.number_input("Tasa Cambio (Bs/$)", min_value=0.1, value=tasa_hoy, format="%.2f")
        
        if st.form_submit_button("Guardar Operación"):
            if not ticker_in:
                st.warning("Escribe un Ticker.")
            elif tipo == "Venta" and cant_in > saldo:
                st.error("No tienes suficientes acciones.")
            else:
                guardar_operacion(ticker_in, cant_in, prec_in, fecha_in, tipo, tasa_in)
                st.success("Guardado!")
                st.rerun()

# --- PROCESAMIENTO DE DATOS ---
if not df_portafolio.empty:
    # Asegurar que existe columna Tasa (para compatibilidad con datos viejos)
    if "Tasa" not in df_portafolio.columns:
        df_portafolio["Tasa"] = tasa_hoy # Relleno por defecto si falta
    
    # 1. Costo Histórico (USD y Bs)
    df_portafolio["Costo Total $"] = df_portafolio["Cantidad"] * df_portafolio["Precio"]
    df_portafolio["Costo Total Bs"] = df_portafolio["Costo Total $"] * df_portafolio["Tasa"] # Usa la tasa histórica
    
    # 2. Agrupar
    df_agrupado = df_portafolio.groupby("Ticker").agg({
        "Cantidad": "sum",
        "Costo Total $": "sum",
        "Costo Total Bs": "sum"
    }).reset_index()
    
    # Filtrar solo activos
    df_final = df_agrupado[df_agrupado["Cantidad"] > 0.00001].copy()
    
    # 3. Precios Actuales
    lista_tickers = df_final["Ticker"].tolist()
    precios_live = obtener_precios_actuales(lista_tickers)
    
    # 4. Cálculos de Valor Actual
    df_final["Precio Actual $"] = df_final["Ticker"].map(precios_live).fillna(0)
    df_final["Valor Hoy $"] = df_final["Cantidad"] * df_final["Precio Actual $"]
    # Para el valor HOY en Bs, usamos la tasa de HOY (no la histórica)
    df_final["Valor Hoy Bs"] = df_final["Valor Hoy $"] * tasa_hoy
    
    # 5. Ganancias
    df_final["Ganancia $"] = df_final["Valor Hoy $"] - df_final["Costo Total $"]
    df_final["Ganancia Bs"] = df_final["Valor Hoy Bs"] - df_final["Costo Total Bs"]

    # --- TABS ---
    tab1, tab2, tab3 = st.tabs(["📊 Mi Portafolio", "🔍 Buscador Mercado", "📅 Reportes"])

    # --- TAB 1: PORTAFOLIO ---
    with tab1:
        st.subheader("Estado Actual")
        
        # Totales
        tot_usd = df_final["Valor Hoy $"].sum()
        gan_usd = df_final["Ganancia $"].sum()
        tot_bs = df_final["Valor Hoy Bs"].sum()
        gan_bs = df_final["Ganancia Bs"].sum()
        
        c1, c2 = st.columns(2)
        c1.metric("Valor Total ($)", f"${tot_usd:,.2f}", delta=f"${gan_usd:,.2f}")
        c2.metric("Valor Total (Bs)", f"Bs. {tot_bs:,.2f}", delta=f"Bs. {gan_bs:,.2f}")
        
        st.divider()
        st.write("### Detalle de mis Acciones")
        
        # Tabla detallada doble moneda
        st.dataframe(df_final[[
            "Ticker", "Cantidad", 
            "Precio Actual $", "Valor Hoy $", "Ganancia $",
            "Valor Hoy Bs", "Ganancia Bs"
        ]].style.format({
            "Cantidad": "{:.4f}",
            "Precio Actual $": "${:.2f}",
            "Valor Hoy $": "${:.2f}",
            "Ganancia $": "${:.2f}",
            "Valor Hoy Bs": "Bs.{:,.2f}",
            "Ganancia Bs": "Bs.{:,.2f}"
        }), use_container_width=True)

    # --- TAB 2: BUSCADOR CON GRÁFICO MODIFICABLE ---
    with tab2:
        col_search, col_period = st.columns([3, 1])
        with col_search:
            search_ticker = st.text_input("🔍 Buscar cualquier acción (Ej: NVDA, MSFT):").upper()
        with col_period:
            # Selector de tiempo para el gráfico
            periodo = st.selectbox("Rango Gráfico:", 
                                   ["1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"], 
                                   index=3) # Default 1y

        if search_ticker:
            tick_obj = yf.Ticker(search_ticker)
            hist = tick_obj.history(period=periodo)
            
            if not hist.empty:
                curr_price = hist["Close"].iloc[-1]
                curr_bs = curr_price * tasa_hoy
                
                m1, m2 = st.columns(2)
                m1.metric(f"Precio {search_ticker} ($)", f"${curr_price:,.2f}")
                m2.metric(f"Precio {search_ticker} (Bs)", f"Bs.{curr_bs:,.2f}", help=f"A tasa BCV hoy: {tasa_hoy}")
                
                st.subheader(f"📈 Comportamiento ({periodo})")
                st.line_chart(hist["Close"])
            else:
                st.warning("No se encontraron datos. Revisa el símbolo.")

    # --- TAB 3: REPORTES ---
    with tab3:
        st.subheader("📜 Historial y Métricas")
        filtro_tiempo = st.selectbox("Filtrar por fecha:", ["Todo", "Última Semana", "Último Mes", "Este Año"])
        
        df_rep = df_portafolio.copy()
        hoy = datetime.now()
        
        if filtro_tiempo == "Última Semana":
            start_date = hoy - timedelta(days=7)
        elif filtro_tiempo == "Último Mes":
            start_date = hoy - timedelta(days=30)
        elif filtro_tiempo == "Este Año":
            start_date = datetime(hoy.year, 1, 1)
        else:
            start_date = datetime(2000, 1, 1)
            
        df_rep = df_rep[df_rep["Fecha"] >= start_date]
        
        if not df_rep.empty:
            inv_periodo = df_rep[df_rep["Tipo"]=="Compra"]["Costo Total $"].sum()
            
            k1, k2 = st.columns(2)
            k1.metric("Invertido en el periodo", f"${inv_periodo:,.2f}")
            k2.metric("Nro. Transacciones", len(df_rep))
            
            st.dataframe(df_rep.sort_values("Fecha", ascending=False).style.format({
                "Precio": "${:.2f}",
                "Tasa": "Bs.{:.2f}",
                "Costo Total $": "${:.2f}",
                "Fecha": "{:%Y-%m-%d}"
            }))
        else:
            st.info("No hay datos para este periodo.")

else:
    st.info("👈 Registra tu primera operación en la barra lateral.")
