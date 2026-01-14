import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Inversiones BVC Pro", page_icon="🇻🇪", layout="wide")

# Estilos CSS para limpiar la interfaz
st.markdown("""
<style>
    .metric-card {background-color: #f0f2f6; border-radius: 10px; padding: 15px;}
    div[data-testid="stMetricValue"] {font-size: 28px;}
</style>
""", unsafe_allow_html=True)

# --- CONEXIÓN A GOOGLE SHEETS ---
# Buscamos una hoja llamada "Portafolio" y otra "Precios"
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos():
    """Carga los datos desde Google Sheets. Si falla, usa datos vacíos."""
    try:
        df_port = conn.read(worksheet="Portafolio", ttl=0) # ttl=0 para no usar caché vieja
        # Asegurar formato de fecha
        df_port["Fecha Compra"] = pd.to_datetime(df_port["Fecha Compra"])
        return df_port
    except:
        # Si es la primera vez o hay error, creamos estructura vacía
        return pd.DataFrame(columns=["Ticker", "Cantidad", "Costo Promedio (Bs)", "Fecha Compra"])

def guardar_compra(ticker, cantidad, costo, fecha):
    """Añade una fila nueva a la hoja de Google Sheets."""
    df_actual = cargar_datos()
    nuevo_registro = pd.DataFrame([{
        "Ticker": ticker,
        "Cantidad": cantidad,
        "Costo Promedio (Bs)": costo,
        "Fecha Compra": pd.to_datetime(fecha)
    }])
    df_actualizado = pd.concat([df_actual, nuevo_registro], ignore_index=True)
    # Escribimos de vuelta en la hoja "Portafolio"
    conn.update(worksheet="Portafolio", data=df_actualizado)
    st.cache_data.clear() # Limpiamos caché para ver cambios inmediato

# --- AUTOMATIZACIÓN (BCV & SCRAPING) ---
@st.cache_data(ttl=3600)
def obtener_tasa_bcv():
    url = "https://www.bcv.org.ve/"
    try:
        response = requests.get(url, verify=False, timeout=5)
        soup = BeautifulSoup(response.content, "html.parser")
        dolar_div = soup.find("div", {"id": "dolar"})
        return float(dolar_div.find("strong").text.strip().replace(',', '.'))
    except:
        return 0.0

# --- INTERFAZ: ENCABEZADO Y TASA ---
st.title("🇻🇪 Mi Portafolio de Inversiones")
st.markdown("---")

# Tasa BCV
tasa_bcv = obtener_tasa_bcv()
col_tasa, col_espacio = st.columns([1, 4])
with col_tasa:
    if tasa_bcv > 0:
        st.metric("Tasa BCV Oficial", f"Bs. {tasa_bcv}", delta="En tiempo real", delta_color="normal")
    else:
        tasa_bcv = st.number_input("⚠️ BCV Caído. Ingresa Tasa Manual:", value=60.0)

# --- CARGAR DATOS ---
df_portafolio = cargar_datos()

# Lista de acciones base
acciones_base = ['BNC', 'MVZ.A', 'TDV.D', 'RST', 'PTN', 'BVL', 'CANTV', 'FVI.B']

# --- BARRA LATERAL (REGISTRO) ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/0/0a/Python.svg/1200px-Python.svg.png", width=50)
    st.header("📝 Registrar Operación")
    
    with st.form("form_compra"):
        ticker_in = st.selectbox("Acción", acciones_base)
        cant_in = st.number_input("Cantidad", min_value=1, value=100)
        costo_in = st.number_input("Precio Compra (Bs)", min_value=0.01, format="%.2f")
        fecha_in = st.date_input("Fecha", datetime.now())
        
        submitted = st.form_submit_button("💾 Guardar en la Nube")
        if submitted:
            guardar_compra(ticker_in, cant_in, costo_in, fecha_in)
            st.success("¡Guardado en Google Sheets!")
            st.rerun()

# --- CUERPO PRINCIPAL ---

# 1. PRECIOS ACTUALES (Manual/Visual)
if 'precios_mercado' not in st.session_state:
    st.session_state.precios_mercado = pd.DataFrame({"Ticker": acciones_base, "Precio Bs.": [0.0]*len(acciones_base)})

st.subheader("📊 Precios de Hoy")
with st.expander("📝 Click aquí para actualizar precios del mercado", expanded=True):
    df_precios = st.data_editor(
        st.session_state.precios_mercado,
        column_config={"Precio Bs.": st.column_config.NumberColumn(format="%.2f Bs")},
        hide_index=True,
        use_container_width=True
    )
    st.session_state.precios_mercado = df_precios

# 2. CÁLCULOS Y VISUALIZACIÓN
if not df_portafolio.empty:
    # Cruce de datos
    df_final = df_portafolio.merge(df_precios, on="Ticker", how="left")
    
    # Matemáticas
    df_final["Inv. Total (Bs)"] = df_final["Cantidad"] * df_final["Costo Promedio (Bs)"]
    df_final["Valor Hoy (Bs)"] = df_final["Cantidad"] * df_final["Precio Bs."]
    df_final["Ganancia (Bs)"] = df_final["Valor Hoy (Bs)"] - df_final["Inv. Total (Bs)"]
    
    # Conversión a Dólares
    df_final["Valor Hoy ($)"] = df_final["Valor Hoy (Bs)"] / tasa_bcv
    df_final["Ganancia ($)"] = df_final["Ganancia (Bs)"] / tasa_bcv
    df_final["Rentabilidad %"] = (df_final["Ganancia (Bs)"] / df_final["Inv. Total (Bs)"]) * 100

    # --- TARJETAS DE RESUMEN (KPIs) ---
    st.markdown("### 💰 Estado de Cuenta")
    k1, k2, k3, k4 = st.columns(4)
    
    total_usd = df_final["Valor Hoy ($)"].sum()
    ganancia_usd = df_final["Ganancia ($)"].sum()
    rentabilidad_total = (df_final["Ganancia (Bs)"].sum() / df_final["Inv. Total (Bs)"].sum()) * 100
    
    k1.metric("Valor Cartera ($)", f"${total_usd:,.2f}")
    k2.metric("Ganancia Neta ($)", f"${ganancia_usd:,.2f}", delta_color="normal")
    k3.metric("Rentabilidad Total", f"{rentabilidad_total:.2f}%", delta="Global")
    k4.metric("Total Invertido (Bs)", f"Bs.{df_final['Inv. Total (Bs)'].sum():,.2f}")

    # --- GRÁFICOS BONITOS ---
    tab1, tab2 = st.tabs(["📈 Distribución & Valor", "📋 Detalle Tabla"])
    
    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            # Gráfico Donut limpio
            fig_pie = px.pie(df_final, values='Valor Hoy ($)', names='Ticker', hole=0.4, title="¿Dónde está mi dinero?")
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)
        with c2:
            # Gráfico Barras coloreadas por ganancia
            fig_bar = px.bar(df_final, x='Ticker', y='Ganancia ($)', color='Ganancia ($)', 
                             title="Ganancia/Pérdida por Acción ($)", color_continuous_scale="RdBu")
            st.plotly_chart(fig_bar, use_container_width=True)

    with tab2:
        st.dataframe(df_final.style.format({
            "Costo Promedio (Bs)": "{:.2f}",
            "Precio Bs.": "{:.2f}",
            "Valor Hoy ($)": "${:.2f}",
            "Ganancia ($)": "${:.2f}",
            "Rentabilidad %": "{:.2f}%"
        }), use_container_width=True)

    # --- SECCIÓN DE REPORTES (¡RESTORED!) ---
    st.markdown("---")
    st.subheader("📅 Reportes Históricos")
    
    filtro_col, _ = st.columns([1, 3])
    with filtro_col:
        periodo = st.selectbox("Filtrar compras realizadas:", ["Todo el Historial", "Última Semana", "Último Mes", "Último Año"])
    
    hoy = datetime.now()
    if periodo == "Última Semana":
        fecha_corte = hoy - timedelta(days=7)
    elif periodo == "Último Mes":
        fecha_corte = hoy - timedelta(days=30)
    elif periodo == "Último Año":
        fecha_corte = hoy - timedelta(days=365)
    else:
        fecha_corte = datetime(2000, 1, 1) # Todo
        
    df_reporte = df_final[df_final["Fecha Compra"] >= pd.to_datetime(fecha_corte)]
    
    if not df_reporte.empty:
        inv_periodo = df_reporte["Inv. Total (Bs)"].sum() / tasa_bcv
        val_periodo = df_reporte["Valor Hoy ($)"].sum()
        st.info(f"Mostrando rendimiento de las acciones compradas en: **{periodo}**")
        
        # Mini resumen del reporte
        r1, r2 = st.columns(2)
        r1.metric("Invertido en este periodo ($)", f"${inv_periodo:,.2f}")
        r2.metric("Valor actual de esas compras", f"${val_periodo:,.2f}", delta=f"{val_periodo-inv_periodo:,.2f} $")
        
        st.dataframe(df_reporte[["Ticker", "Fecha Compra", "Cantidad", "Ganancia ($)", "Rentabilidad %"]])
    else:
        st.warning(f"No hiciste compras en {periodo}.")

else:
    st.info("👈 ¡Tu portafolio está vacío! Registra tu primera compra en la barra lateral para empezar.")

