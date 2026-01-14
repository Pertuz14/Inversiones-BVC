import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Inversiones BVC Pro", page_icon="🇻🇪", layout="wide")

# Estilos CSS
st.markdown("""
<style>
    .metric-card {background-color: #f0f2f6; border-radius: 10px; padding: 15px;}
    div[data-testid="stMetricValue"] {font-size: 28px;}
</style>
""", unsafe_allow_html=True)

# --- CONEXIÓN A GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos():
    """Carga los datos desde Google Sheets."""
    try:
        df_port = conn.read(worksheet="Portafolio", ttl=0)
        df_port["Fecha Compra"] = pd.to_datetime(df_port["Fecha Compra"])
        return df_port
    except:
        # Estructura base si está vacío
        return pd.DataFrame(columns=[
            "Ticker", "Cantidad", "Precio Compra (Bs)", 
            "Fecha Compra", "Tasa Cambio (Bs/$)", 
            "Total Invertido (Bs)", "Total Invertido ($)"
        ])

def guardar_compra(ticker, cantidad, costo, fecha, tasa_registro):
    """Calcula los totales y guarda la fila en formato tabla en Sheets."""
    df_actual = cargar_datos()
    
    # Cálculos para el registro histórico
    total_bs = cantidad * costo
    total_usd = total_bs / tasa_registro if tasa_registro > 0 else 0
    
    nuevo_registro = pd.DataFrame([{
        "Ticker": ticker,
        "Cantidad": cantidad,
        "Precio Compra (Bs)": costo,
        "Fecha Compra": pd.to_datetime(fecha),
        "Tasa Cambio (Bs/$)": tasa_registro,      # <--- Tasa del día guardada
        "Total Invertido (Bs)": total_bs,         # <--- Total en Bolívares guardado
        "Total Invertido ($)": total_usd          # <--- Equivalente en Dólares guardado
    }])
    
    # Unimos y sobrescribimos la hoja para mantener el formato de tabla limpia
    df_actualizado = pd.concat([df_actual, nuevo_registro], ignore_index=True)
    conn.update(worksheet="Portafolio", data=df_actualizado)
    st.cache_data.clear()

# --- AUTOMATIZACIÓN (BCV) ---
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

# --- INTERFAZ ---
st.title("🇻🇪 Mi Portafolio de Inversiones")
st.markdown("---")

# Obtener Tasa (para usarla en el guardado)
tasa_bcv = obtener_tasa_bcv()
tasa_uso = 0.0

# Mostrar Tasa y definir cuál usar
col_tasa, col_espacio = st.columns([1, 4])
with col_tasa:
    if tasa_bcv > 0:
        st.metric("Tasa BCV Oficial", f"Bs. {tasa_bcv}", delta="En tiempo real", delta_color="normal")
        tasa_uso = tasa_bcv
    else:
        tasa_uso = st.number_input("⚠️ BCV Caído. Ingresa Tasa Manual:", value=60.0)

# Cargar Portafolio
df_portafolio = cargar_datos()
acciones_base = ['BNC', 'MVZ.A', 'TDV.D', 'RST', 'PTN', 'BVL', 'CANTV', 'FVI.B']

# --- BARRA LATERAL (REGISTRO ACTUALIZADO) ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/0/0a/Python.svg/1200px-Python.svg.png", width=50)
    st.header("📝 Registrar Operación")
    
    with st.form("form_compra"):
        st.info(f"Tasa a registrar: Bs. {tasa_uso}") # Feedback visual
        
        ticker_in = st.selectbox("Acción", acciones_base)
        cant_in = st.number_input("Cantidad", min_value=1, value=100)
        costo_in = st.number_input("Precio Compra (Bs)", min_value=0.01, format="%.2f")
        fecha_in = st.date_input("Fecha", datetime.now())
        
        submitted = st.form_submit_button("💾 Guardar Transacción")
        if submitted:
            # Enviamos la tasa_uso a la función de guardado
            guardar_compra(ticker_in, cant_in, costo_in, fecha_in, tasa_uso)
            st.success("¡Transacción registrada exitosamente!")
            st.rerun()

# --- CUERPO PRINCIPAL ---
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

# CÁLCULOS
if not df_portafolio.empty:
    # Usamos "Precio Compra (Bs)" para los cálculos históricos
    df_final = df_portafolio.merge(df_precios, on="Ticker", how="left")
    
    # Matemáticas
    df_final["Inv. Total (Bs)"] = df_final["Total Invertido (Bs)"] # Usamos el dato guardado
    df_final["Valor Hoy (Bs)"] = df_final["Cantidad"] * df_final["Precio Bs."]
    df_final["Ganancia (Bs)"] = df_final["Valor Hoy (Bs)"] - df_final["Inv. Total (Bs)"]
    
    # Conversión a Dólares (Valor actual vs Inversión histórica en $)
    df_final["Valor Hoy ($)"] = df_final["Valor Hoy (Bs)"] / tasa_uso
    df_final["Inv. Total ($)"] = df_final["Total Invertido ($)"] # Dato histórico
    df_final["Ganancia ($)"] = df_final["Valor Hoy ($)"] - df_final["Inv. Total ($)"]
    
    # Evitar división por cero
    df_final["Rentabilidad %"] = df_final.apply(
        lambda x: (x["Ganancia ($)"] / x["Inv. Total ($)"] * 100) if x["Inv. Total ($)"] > 0 else 0, axis=1
    )

    # --- KPIs ---
    st.markdown("### 💰 Estado de Cuenta")
    k1, k2, k3, k4 = st.columns(4)
    
    total_usd = df_final["Valor Hoy ($)"].sum()
    ganancia_usd = df_final["Ganancia ($)"].sum()
    inv_total_usd = df_final["Inv. Total ($)"].sum()
    rentabilidad_total = ((total_usd - inv_total_usd) / inv_total_usd * 100) if inv_total_usd > 0 else 0
    
    k1.metric("Valor Cartera ($)", f"${total_usd:,.2f}")
    k2.metric("Ganancia Neta ($)", f"${ganancia_usd:,.2f}", delta_color="normal")
    k3.metric("Rentabilidad Total", f"{rentabilidad_total:.2f}%", delta="Global")
    k4.metric("Total Invertido ($)", f"${inv_total_usd:,.2f}")

    # --- GRÁFICOS Y TABLA ---
    tab1, tab2 = st.tabs(["📈 Distribución & Valor", "📋 Detalle Tabla"])
    
    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            fig_pie = px.pie(df_final, values='Valor Hoy ($)', names='Ticker', hole=0.4, title="¿Dónde está mi dinero?")
            st.plotly_chart(fig_pie, use_container_width=True)
        with c2:
            fig_bar = px.bar(df_final, x='Ticker', y='Ganancia ($)', color='Ganancia ($)', 
                             title="Ganancia/Pérdida por Acción ($)", color_continuous_scale="RdBu")
            st.plotly_chart(fig_bar, use_container_width=True)

    with tab2:
        # Mostramos la tabla completa con los nuevos datos históricos
        st.dataframe(df_final[[
            "Ticker", "Cantidad", "Fecha Compra", 
            "Precio Compra (Bs)", "Tasa Cambio (Bs/$)", 
            "Total Invertido (Bs)", "Total Invertido ($)", 
            "Valor Hoy ($)", "Ganancia ($)", "Rentabilidad %"
        ]].style.format({
            "Precio Compra (Bs)": "{:.2f}",
            "Tasa Cambio (Bs/$)": "{:.2f}",
            "Total Invertido (Bs)": "{:.2f}",
            "Total Invertido ($)": "${:.2f}",
            "Valor Hoy ($)": "${:.2f}",
            "Ganancia ($)": "${:.2f}",
            "Rentabilidad %": "{:.2f}%"
        }), use_container_width=True)

    # --- REPORTES ---
    st.markdown("---")
    st.subheader("📅 Reportes Históricos")
    periodo = st.selectbox("Filtrar por:", ["Todo el Historial", "Última Semana", "Último Mes", "Último Año"])
    
    hoy = datetime.now()
    if periodo == "Última Semana": fecha_corte = hoy - timedelta(days=7)
    elif periodo == "Último Mes": fecha_corte = hoy - timedelta(days=30)
    elif periodo == "Último Año": fecha_corte = hoy - timedelta(days=365)
    else: fecha_corte = datetime(2000, 1, 1)
        
    df_reporte = df_final[df_final["Fecha Compra"] >= pd.to_datetime(fecha_corte)]
    
    if not df_reporte.empty:
        st.info(f"Mostrando: {periodo}")
        st.dataframe(df_reporte)
    else:
        st.warning(f"No hay datos para {periodo}.")

else:
    st.info("👈 Registra tu primera compra para empezar.")
