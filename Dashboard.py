import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Inversiones BVC Pro", page_icon="🇻🇪", layout="wide")

st.markdown("""
<style>
    .metric-card {background-color: #f0f2f6; border-radius: 10px; padding: 15px;}
    div[data-testid="stMetricValue"] {font-size: 28px;}
</style>
""", unsafe_allow_html=True)

# --- CONEXIÓN GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos():
    try:
        df = conn.read(worksheet="Portafolio", ttl=0)
        df["Fecha Compra"] = pd.to_datetime(df["Fecha Compra"])
        return df
    except:
        return pd.DataFrame(columns=[
            "Ticker", "Cantidad", "Precio Operacion (Bs)", 
            "Fecha Compra", "Tasa Cambio (Bs/$)", 
            "Total Operacion (Bs)", "Total Operacion ($)", "Tipo"
        ])

def guardar_transaccion(ticker, cantidad, precio, fecha, tasa, tipo):
    """Guarda compras (positivo) o ventas (negativo)."""
    df_actual = cargar_datos()
    
    # Si es venta, la cantidad y los totales se guardan en negativo para restar
    cantidad_final = cantidad if tipo == "Compra" else -cantidad
    
    total_bs = abs(cantidad * precio) # El monto de dinero siempre es absoluto
    if tipo == "Venta": total_bs = total_bs * -1 # Pero contablemente sale del activo
        
    total_usd = total_bs / tasa if tasa > 0 else 0
    
    nuevo = pd.DataFrame([{
        "Ticker": ticker,
        "Cantidad": cantidad_final,
        "Precio Operacion (Bs)": precio,
        "Fecha Compra": pd.to_datetime(fecha),
        "Tasa Cambio (Bs/$)": tasa,
        "Total Operacion (Bs)": total_bs,
        "Total Operacion ($)": total_usd,
        "Tipo": tipo
    }])
    
    df_updated = pd.concat([df_actual, nuevo], ignore_index=True)
    conn.update(worksheet="Portafolio", data=df_updated)
    st.cache_data.clear()

# --- FUNCIONES DE CÁLCULO AVANZADO ---
def procesar_portafolio(df_raw):
    """Convierte la lista de transacciones en un resumen de tenencias actuales."""
    if df_raw.empty: return pd.DataFrame()

    resumen = []
    tickers = df_raw['Ticker'].unique()

    for t in tickers:
        df_t = df_raw[df_raw['Ticker'] == t]
        
        # 1. Calcular Cantidad Actual
        cantidad_actual = df_t['Cantidad'].sum()
        
        # 2. Calcular Costo Promedio (Solo de las compras)
        compras = df_t[df_t['Cantidad'] > 0]
        if not compras.empty:
            costo_promedio_bs = (compras['Cantidad'] * compras['Precio Operacion (Bs)']).sum() / compras['Cantidad'].sum()
            costo_promedio_usd = (compras['Cantidad'] * (compras['Total Operacion (Bs)'] / compras['Tasa Cambio (Bs/$)'])).sum() / compras['Cantidad'].sum()
        else:
            costo_promedio_bs = 0
            costo_promedio_usd = 0
            
        if cantidad_actual > 0:
            resumen.append({
                "Ticker": t,
                "Cantidad": cantidad_actual,
                "Costo Promedio (Bs)": costo_promedio_bs,
                "Inv. Historica ($)": cantidad_actual * costo_promedio_usd # Cuánto me costaron las acciones que ME QUEDAN
            })
            
    return pd.DataFrame(resumen)

# --- AUTOMATIZACIÓN BCV ---
@st.cache_data(ttl=3600)
def obtener_tasa_bcv():
    try:
        r = requests.get("https://www.bcv.org.ve/", verify=False, timeout=5)
        soup = BeautifulSoup(r.content, "html.parser")
        return float(soup.find("div", {"id": "dolar"}).find("strong").text.strip().replace(',', '.'))
    except:
        return 0.0

# --- INTERFAZ ---
st.title("🇻🇪 Mi Portafolio de Inversiones")
st.markdown("---")

tasa_bcv = obtener_tasa_bcv()
tasa_uso = tasa_bcv if tasa_bcv > 0 else st.number_input("⚠️ BCV Offline. Tasa Manual:", value=60.0)

if tasa_bcv > 0:
    st.metric("Tasa BCV", f"Bs. {tasa_bcv}", delta="En línea")

# Cargar Historial Completo
df_historial = cargar_datos()
df_tenencias = procesar_portafolio(df_historial)

acciones_base = ['BNC', 'MVZ.A', 'TDV.D', 'RST', 'PTN', 'BVL', 'CANTV', 'FVI.B']

# --- BARRA LATERAL (COMPRA / VENTA) ---
with st.sidebar:
    st.header("Operaciones")
    tipo_op = st.radio("Acción:", ["Comprar", "Vender"], horizontal=True)
    
    with st.form("form_ops"):
        ticker = st.selectbox("Acción", acciones_base)
        
        # Feedback de cuántas tienes
        cant_actual = 0
        if not df_tenencias.empty and ticker in df_tenencias['Ticker'].values:
            cant_actual = df_tenencias[df_tenencias['Ticker'] == ticker]['Cantidad'].values[0]
        
        if tipo_op == "Vender":
            st.info(f"Tienes disponible: {cant_actual} acciones")
        
        cantidad = st.number_input("Cantidad", min_value=1, value=100)
        precio = st.number_input(f"Precio {tipo_op} (Bs)", min_value=0.01, format="%.2f")
        fecha = st.date_input("Fecha", datetime.now())
        
        submitted = st.form_submit_button(f"Confirmar {tipo_op}")
        
        if submitted:
            if tipo_op == "Vender" and cantidad > cant_actual:
                st.error(f"¡Error! No puedes vender {cantidad} porque solo tienes {cant_actual}.")
            else:
                guardar_transaccion(ticker, cantidad, precio, fecha, tasa_uso, tipo_op)
                st.success("Transacción registrada.")
                st.rerun()

# --- DASHBOARD PRINCIPAL ---

# Precios Actuales
if 'precios_mercado' not in st.session_state:
    st.session_state.precios_mercado = pd.DataFrame({"Ticker": acciones_base, "Precio Bs.": [0.0]*len(acciones_base)})

st.subheader("📊 Precios de Hoy")
with st.expander("📝 Actualizar Precios Mercado", expanded=True):
    edited_prices = st.data_editor(
        st.session_state.precios_mercado,
        column_config={"Precio Bs.": st.column_config.NumberColumn(format="%.2f Bs")},
        hide_index=True,
        use_container_width=True
    )
    st.session_state.precios_mercado = edited_prices

if not df_tenencias.empty:
    # Unir tenencias con precios actuales
    df_final = df_tenencias.merge(edited_prices, on="Ticker", how="left")
    
    # Cálculos Finales
    df_final["Valor Hoy (Bs)"] = df_final["Cantidad"] * df_final["Precio Bs."]
    df_final["Valor Hoy ($)"] = df_final["Valor Hoy (Bs)"] / tasa_uso
    
    # Ganancia NO Realizada (Paper money)
    df_final["Ganancia ($)"] = df_final["Valor Hoy ($)"] - df_final["Inv. Historica ($)"]
    
    df_final["Rentabilidad %"] = df_final.apply(
        lambda x: (x["Ganancia ($)"] / x["Inv. Historica ($)"] * 100) if x["Inv. Historica ($)"] > 0 else 0, axis=1
    )

    # KPIs Globales
    st.markdown("### 💰 Resumen Financiero")
    k1, k2, k3, k4 = st.columns(4)
    
    total_val_usd = df_final["Valor Hoy ($)"].sum()
    total_cost_usd = df_final["Inv. Historica ($)"].sum()
    ganancia_total = total_val_usd - total_cost_usd
    rent_total = (ganancia_total / total_cost_usd * 100) if total_cost_usd > 0 else 0
    
    k1.metric("Valor Cartera ($)", f"${total_val_usd:,.2f}")
    k2.metric("Ganancia Latente ($)", f"${ganancia_total:,.2f}", delta_color="normal")
    k3.metric("Rentabilidad Total", f"{rent_total:.2f}%", delta="Global")
    k4.metric("Costo Base ($)", f"${total_cost_usd:,.2f}", help="Dinero invertido en las acciones que aún posees")

    # Gráficos
    tab1, tab2, tab3 = st.tabs(["📈 Gráficos", "📋 Tenencias Actuales", "📖 Historial Transacciones"])
    
    with tab1:
        c1, c2 = st.columns(2)
        c1.plotly_chart(px.pie(df_final, values='Valor Hoy ($)', names='Ticker', hole=0.4, title="Distribución ($)"), use_container_width=True)
        c2.plotly_chart(px.bar(df_final, x='Ticker', y='Ganancia ($)', color='Ganancia ($)', title="Ganancia/Pérdida ($)", color_continuous_scale="RdBu"), use_container_width=True)

    with tab2:
        st.dataframe(df_final.style.format({
            "Costo Promedio (Bs)": "{:.2f}",
            "Precio Bs.": "{:.2f}",
            "Valor Hoy ($)": "${:.2f}",
            "Ganancia ($)": "${:.2f}",
            "Rentabilidad %": "{:.2f}%",
            "Inv. Historica ($)": "${:.2f}"
        }), use_container_width=True)
        
    with tab3:
        st.write("Registro de todas tus compras y ventas:")
        st.dataframe(df_historial.sort_values(by="Fecha Compra", ascending=False))

else:
    st.info("👈 Registra tu primera operación.")
