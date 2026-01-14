import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Inversiones BVC", layout="wide")

# --- FUNCIONES DE AUTOMATIZACIÓN (SCRAPING) ---

@st.cache_data(ttl=3600) # Guarda el dato por 1 hora para no saturar
def obtener_tasa_bcv():
    """Intenta obtener la tasa del Dólar oficial del BCV."""
    url = "https://www.bcv.org.ve/"
    try:
        # El BCV a veces tiene problemas de certificado SSL, lo ignoramos con verify=False
        response = requests.get(url, verify=False, timeout=5)
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Buscamos el div específico donde el BCV publica el dolar
        dolar_div = soup.find("div", {"id": "dolar"})
        tasa_texto = dolar_div.find("strong").text.strip().replace(',', '.')
        return float(tasa_texto)
    except Exception as e:
        return 0.0 # Si falla, devolveremos 0 para pedir manual

# --- GESTIÓN DE ESTADO ---
if 'portafolio' not in st.session_state:
    st.session_state.portafolio = pd.DataFrame(columns=["Ticker", "Cantidad", "Costo Promedio (Bs)", "Fecha Compra"])

# Acciones predefinidas para monitorear
acciones_base = ['BNC', 'MVZ.A', 'TDV.D', 'RST', 'PTN', 'BVL', 'CANTV', 'FVI.B']

if 'precios_mercado' not in st.session_state:
    st.session_state.precios_mercado = pd.DataFrame({
        "Ticker": acciones_base,
        "Precio Bs.": [0.0] * len(acciones_base)
    })

# --- INTERFAZ ---
st.title("🇻🇪 Monitor BVC & Dólar BCV")

# 1. BARRA SUPERIOR: TASA BCV
tasa_bcv_auto = obtener_tasa_bcv()

col_tasa1, col_tasa2 = st.columns([1, 3])
with col_tasa1:
    st.markdown("### 🏦 Tasa BCV")
    if tasa_bcv_auto > 0:
        st.success(f"Detectada: {tasa_bcv_auto} Bs./$")
        tasa_uso = tasa_bcv_auto
    else:
        st.warning("No se pudo leer el BCV (Página caída/lenta)")
        tasa_uso = st.number_input("Ingresa Tasa Manual:", value=60.0, min_value=1.0)

# 2. BARRA LATERAL: COMPRAS
with st.sidebar:
    st.header("📝 Registrar Compra")
    ticker_input = st.selectbox("Acción", acciones_base)
    cantidad_input = st.number_input("Cantidad", min_value=1, value=100)
    costo_input = st.number_input("Costo Unitario (Bs.)", min_value=0.01, format="%.2f")
    fecha_input = st.date_input("Fecha", datetime.now())
    
    if st.button("Guardar"):
        nuevo = pd.DataFrame([{
            "Ticker": ticker_input, 
            "Cantidad": cantidad_input, 
            "Costo Promedio (Bs)": costo_input,
            "Fecha Compra": pd.to_datetime(fecha_input)
        }])
        st.session_state.portafolio = pd.concat([st.session_state.portafolio, nuevo], ignore_index=True)
        st.success("Guardado.")

# 3. PRECIOS ACTUALES (Automático o Manual)
st.subheader("📈 Precios del Mercado (Bs.)")
st.info("💡 Si la automatización falla, haz doble click en la celda para corregir el precio.")

# Editor de precios
df_precios = st.data_editor(
    st.session_state.precios_mercado,
    key="editor_precios",
    column_config={
        "Precio Bs.": st.column_config.NumberColumn(format="%.2f Bs")
    },
    hide_index=True
)
st.session_state.precios_mercado = df_precios

# 4. CÁLCULOS Y DASHBOARD
df_port = st.session_state.portafolio

if not df_port.empty and tasa_uso > 0:
    # Unir datos
    df_final = df_port.merge(df_precios, on="Ticker", how="left")
    
    # Cálculos en Bolívares
    df_final["Valor Costo (Bs)"] = df_final["Cantidad"] * df_final["Costo Promedio (Bs)"]
    df_final["Valor Mercado (Bs)"] = df_final["Cantidad"] * df_final["Precio Bs."]
    df_final["Ganancia (Bs)"] = df_final["Valor Mercado (Bs)"] - df_final["Valor Costo (Bs)"]
    
    # Cálculos en Dólares (BCV)
    df_final["Valor Mercado ($)"] = df_final["Valor Mercado (Bs)"] / tasa_uso
    df_final["Ganancia ($)"] = df_final["Ganancia (Bs)"] / tasa_uso
    
    # --- MÉTRICAS ---
    st.markdown("---")
    total_bs = df_final["Valor Mercado (Bs)"].sum()
    total_usd = df_final["Valor Mercado ($)"].sum()
    ganancia_usd = df_final["Ganancia ($)"].sum()
    
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Valor Total Cartera (Bs)", f"Bs. {total_bs:,.2f}")
    kpi2.metric("Valor Total Cartera ($)", f"$ {total_usd:,.2f}", help=f"Calculado a tasa BCV: {tasa_uso}")
    kpi3.metric("Ganancia/Pérdida ($)", f"$ {ganancia_usd:,.2f}", delta_color="normal")
    
    # --- GRÁFICOS ---
    g1, g2 = st.columns(2)
    with g1:
        # Gráfico en Dólares
        fig = px.bar(df_final, x='Ticker', y='Valor Mercado ($)', title='Valor de Posiciones en USD ($)')
        st.plotly_chart(fig, use_container_width=True)
    with g2:
        # Tabla resumen
        st.subheader("Detalle Financiero")
        vista_simple = df_final[["Ticker", "Cantidad", "Precio Bs.", "Valor Mercado ($)", "Ganancia ($)"]]
        st.dataframe(vista_simple.style.format({
            "Precio Bs.": "{:.2f}",
            "Valor Mercado ($)": "${:.2f}",
            "Ganancia ($)": "${:.2f}"
        }), hide_index=True)

else:
    st.write("👈 Registra tu primera compra para ver los cálculos.")

