import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Inversiones BVC Pro", page_icon="🇻🇪", layout="wide")

# Estilos CSS (Igual que antes)
st.markdown("""
<style>
    .metric-card {background-color: #f0f2f6; border-radius: 10px; padding: 15px;}
    div[data-testid="stMetricValue"] {font-size: 28px;}
</style>
""", unsafe_allow_html=True)

# --- CONEXIÓN A GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos():
    """Carga los datos. Si no hay columna 'Tipo', la crea."""
    try:
        df_port = conn.read(worksheet="Portafolio", ttl=0)
        df_port["Fecha Compra"] = pd.to_datetime(df_port["Fecha Compra"])
        # Compatibilidad: Si la columna Tipo no existe (datos viejos), rellenar con "Compra"
        if "Tipo" not in df_port.columns:
            df_port["Tipo"] = "Compra"
        return df_port
    except:
        return pd.DataFrame(columns=[
            "Ticker", "Cantidad", "Precio Operacion (Bs)", 
            "Fecha Compra", "Tasa Cambio (Bs/$)", 
            "Total Invertido (Bs)", "Total Invertido ($)", "Tipo"
        ])

def guardar_operacion(ticker, cantidad, precio, fecha, tasa_registro, tipo):
    """Guarda Compra (Positivo) o Venta (Negativo)."""
    df_actual = cargar_datos()
    
    # --- LOGICA NUEVA PARA VENTAS ---
    # Si es VENTA, guardamos los valores en NEGATIVO para que resten en los cálculos
    cantidad_final = cantidad
    if tipo == "Venta":
        cantidad_final = -cantidad 
    
    # Calculamos totales
    total_bs = cantidad_final * precio
    total_usd = total_bs / tasa_registro if tasa_registro > 0 else 0
    
    nuevo_registro = pd.DataFrame([{
        "Ticker": ticker,
        "Cantidad": cantidad_final,
        "Precio Operacion (Bs)": precio,
        "Fecha Compra": pd.to_datetime(fecha),
        "Tasa Cambio (Bs/$)": tasa_registro,
        "Total Invertido (Bs)": total_bs,
        "Total Invertido ($)": total_usd,
        "Tipo": tipo  # <--- Guardamos si fue Compra o Venta
    }])
    
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

# Tasa BCV
tasa_bcv = obtener_tasa_bcv()
tasa_uso = 0.0

col_tasa, col_espacio = st.columns([1, 4])
with col_tasa:
    if tasa_bcv > 0:
        st.metric("Tasa BCV Oficial", f"Bs. {tasa_bcv}", delta="En tiempo real", delta_color="normal")
        tasa_uso = tasa_bcv
    else:
        tasa_uso = st.number_input("⚠️ BCV Caído. Ingresa Tasa Manual:", value=60.0)

df_portafolio = cargar_datos()
acciones_base = ['BNC', 'MVZ.A', 'TDV.D', 'RST', 'PTN', 'BVL', 'CANTV', 'FVI.B']

# --- BARRA LATERAL (MODIFICADA PARA VENTAS) ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/0/0a/Python.svg/1200px-Python.svg.png", width=50)
    st.header("📝 Registrar Operación")
    
    # 1. Selector de Tipo
    tipo_operacion = st.radio("¿Qué quieres hacer?", ["Compra", "Venta"], horizontal=True)

    with st.form("form_compra"):
        st.info(f"Tasa registro: Bs. {tasa_uso}")
        
        ticker_in = st.selectbox("Acción", acciones_base)
        
        # Validación de Saldo (Solo visual)
        saldo_actual = 0
        if not df_portafolio.empty and ticker_in in df_portafolio["Ticker"].values:
            saldo_actual = df_portafolio[df_portafolio["Ticker"] == ticker_in]["Cantidad"].sum()
        
        if tipo_operacion == "Venta":
            st.caption(f"⚠️ Tienes {saldo_actual} acciones disponibles.")
        
        cant_in = st.number_input("Cantidad", min_value=1, value=100)
        costo_in = st.number_input(f"Precio {tipo_operacion} (Bs)", min_value=0.01, format="%.2f")
        fecha_in = st.date_input("Fecha", datetime.now())
        
        submitted = st.form_submit_button(f"💾 Registrar {tipo_operacion}")
        
        if submitted:
            # VALIDACIÓN: No vender lo que no tienes
            if tipo_operacion == "Venta" and cant_in > saldo_actual:
                st.error(f"❌ Error: No puedes vender {cant_in} acciones. Solo tienes {saldo_actual}.")
            else:
                guardar_operacion(ticker_in, cant_in, costo_in, fecha_in, tasa_uso, tipo_operacion)
                st.success(f"¡{tipo_operacion} registrada con éxito!")
                st.rerun()

# --- CUERPO PRINCIPAL (SIN CAMBIOS VISUALES) ---
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

# CÁLCULOS (Automáticamente maneja las ventas porque restan cantidad)
if not df_portafolio.empty:
    
    # Agrupar datos para evitar filas duplicadas negativas en la tabla visual
    # (Opcional, pero dejaremos el detalle transacción por transacción como pediste antes)
    df_final = df_portafolio.merge(df_precios, on="Ticker", how="left")
    
    # Usamos las columnas que ya vienen de la hoja (Total Invertido puede ser negativo si fue venta)
    df_final["Inv. Total (Bs)"] = df_final["Total Invertido (Bs)"]
    
    # Valor Hoy = Cantidad (positiva o negativa) * Precio Actual
    # Nota: Las filas de Venta tendrán cantidad negativa, lo que reducirá el valor total del portafolio. Correcto.
    df_final["Valor Hoy (Bs)"] = df_final["Cantidad"] * df_final["Precio Bs."]
    
    # Ganancia = Valor Hoy - Inversión Original
    # En ventas: (Negativo - Negativo) tiende a neutralizar la fila, ajustando el total global.
    df_final["Ganancia (Bs)"] = df_final["Valor Hoy (Bs)"] - df_final["Inv. Total (Bs)"]
    
    # Conversión a Dólares
    df_final["Valor Hoy ($)"] = df_final["Valor Hoy (Bs)"] / tasa_uso
    df_final["Inv. Total ($)"] = df_final["Total Invertido ($)"]
    df_final["Ganancia ($)"] = df_final["Valor Hoy ($)"] - df_final["Inv. Total ($)"]
    
    # Rentabilidad
    df_final["Rentabilidad %"] = df_final.apply(
        lambda x: (x["Ganancia ($)"] / x["Inv. Total ($)"] * 100) if x["Inv. Total ($)"] != 0 else 0, axis=1
    )

   # --- KPIs (MODIFICADO: DUAL CURRENCY) ---
    st.markdown("### 💰 Estado de Cuenta")
    
    # 1. Calculamos los totales en ambas monedas
    total_bs = df_final["Valor Hoy (Bs)"].sum()
    total_usd = df_final["Valor Hoy ($)"].sum()
    
    inv_total_bs = df_final["Inv. Total (Bs)"].sum()
    inv_total_usd = df_final["Inv. Total ($)"].sum()
    
    ganancia_bs = df_final["Ganancia (Bs)"].sum()
    ganancia_usd = df_final["Ganancia ($)"].sum()
    
    # Rentabilidad (se calcula en base a dólares que es la moneda fuerte de referencia)
    rent_total = ((total_usd - inv_total_usd) / inv_total_usd * 100) if inv_total_usd != 0 else 0
    
    # 2. Fila Principal: DÓLARES ($)
    st.markdown("##### 💵 Referencia en Divisas")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Valor Cartera ($)", f"${total_usd:,.2f}")
    k2.metric("Ganancia Neta ($)", f"${ganancia_usd:,.2f}", delta_color="normal")
    k3.metric("Total Invertido ($)", f"${inv_total_usd:,.2f}")
    k4.metric("Rentabilidad Global", f"{rent_total:.2f}%")

    # 3. Fila Secundaria: BOLÍVARES (Bs)
    st.markdown("##### 🇻🇪 Referencia en Bolívares")
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Valor Cartera (Bs)", f"Bs. {total_bs:,.2f}")
    b2.metric("Ganancia Neta (Bs)", f"Bs. {ganancia_bs:,.2f}", delta_color="normal")
    b3.metric("Total Invertido (Bs)", f"Bs. {inv_total_bs:,.2f}")
    b4.empty() # Espacio vacío para alinear
    
    # --- GRÁFICOS ---
    tab1, tab2 = st.tabs(["📈 Distribución & Valor", "📋 Detalle Tabla"])
    
    # Preparamos datos agrupados SOLO para el gráfico (para no ver sectores negativos)
    df_agrupado = df_final.groupby("Ticker")[["Valor Hoy ($)", "Ganancia ($)"]].sum().reset_index()
    df_agrupado = df_agrupado[df_agrupado["Valor Hoy ($)"] > 0] # Solo mostrar lo que tenemos

    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            fig_pie = px.pie(df_agrupado, values='Valor Hoy ($)', names='Ticker', hole=0.4, title="¿Dónde está mi dinero?")
            st.plotly_chart(fig_pie, use_container_width=True)
        with c2:
            fig_bar = px.bar(df_final, x='Ticker', y='Ganancia ($)', color='Ganancia ($)', 
                             title="Histórico de Operaciones ($)", color_continuous_scale="RdBu")
            st.plotly_chart(fig_bar, use_container_width=True)

    with tab2:
        # Tabla detallada con la nueva columna TIPO
        cols_mostrar = ["Tipo", "Ticker", "Cantidad", "Fecha Compra", "Precio Operacion (Bs)", "Total Invertido ($)", "Ganancia ($)", "Rentabilidad %"]
        
        # Renombrar columna para que coincida con la lectura
        df_mostrar = df_final.rename(columns={"Precio Compra (Bs)": "Precio Operacion (Bs)"})
        
        # Asegurarnos de que las columnas existan antes de mostrar
        cols_finales = [c for c in cols_mostrar if c in df_mostrar.columns]
        
        st.dataframe(df_mostrar[cols_finales].style.format({
            "Precio Operacion (Bs)": "{:.2f}",
            "Total Invertido ($)": "${:.2f}",
            "Ganancia ($)": "${:.2f}",
            "Rentabilidad %": "{:.2f}%"
        }), use_container_width=True)

    # --- REPORTES ---
    st.markdown("---")
    st.subheader("📅 Reportes Históricos")
    periodo = st.selectbox("Filtrar operaciones:", ["Todo el Historial", "Última Semana", "Último Mes", "Último Año"])
    
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
        st.warning(f"No hay movimientos para {periodo}.")

else:
    st.info("👈 Registra tu primera compra para empezar.")
