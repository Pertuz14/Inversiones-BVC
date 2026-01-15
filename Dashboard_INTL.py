import streamlit as st
import pandas as pd
import plotly.express as px
import yfinance as yf
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Wall St. Portfolio", page_icon="🇺🇸", layout="wide")

# Estilos
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
        # OJO: Lee la pestaña nueva "Portafolio_INTL"
        df = conn.read(worksheet="Portafolio_INTL", ttl=0)
        df["Fecha"] = pd.to_datetime(df["Fecha"])
        return df
    except:
        return pd.DataFrame(columns=["Ticker", "Cantidad", "Precio", "Fecha", "Tipo"])

def guardar_operacion(ticker, cantidad, precio, fecha, tipo):
    df_actual = cargar_datos()
    
    # Lógica de signos (Venta resta cantidad)
    qty_final = cantidad if tipo == "Compra" else -cantidad
    
    nuevo = pd.DataFrame([{
        "Ticker": ticker.upper(),
        "Cantidad": qty_final,
        "Precio": precio,
        "Fecha": pd.to_datetime(fecha),
        "Tipo": tipo
    }])
    
    df_updated = pd.concat([df_actual, nuevo], ignore_index=True)
    conn.update(worksheet="Portafolio_INTL", data=df_updated)
    st.cache_data.clear()

# --- FUNCIÓN MÁGICA: PRECIOS EN VIVO (YAHOO FINANCE) ---
def obtener_precios_actuales(lista_tickers):
    if not lista_tickers: return {}
    
    st.toast("📡 Conectando con Wall Street...", icon="🇺🇸")
    try:
        # Descarga masiva de precios
        datos = yf.download(lista_tickers, period="1d")['Close']
        precios = {}
        
        # Si es un solo ticker, yfinance devuelve una Serie, no un DataFrame
        if len(lista_tickers) == 1:
            val = datos.iloc[-1]
            precios[lista_tickers[0]] = float(val)
        else:
            # Para varios tickers
            current = datos.iloc[-1]
            for tick in lista_tickers:
                # Manejo de error si un ticker no existe
                if tick in current:
                    precios[tick] = float(current[tick])
        return precios
    except Exception as e:
        st.error(f"Error conectando a Yahoo Finance: {e}")
        return {}

# --- INTERFAZ ---
st.title("🌎 Mi Portafolio Internacional")
st.markdown("---")

df_portafolio = cargar_datos()

# --- BARRA LATERAL (REGISTRO) ---
with st.sidebar:
    st.header("📝 Nueva Operación")
    tipo = st.radio("Acción:", ["Compra", "Venta"], horizontal=True)
    
    with st.form("entry_form"):
        # Input de texto libre (para poner AAPL, TSLA, NVDA, VOO, etc)
        ticker_in = st.text_input("Ticker (Ej: AAPL, BTC-USD)").upper()
        
        # Mostrar saldo si ya tengo esa acción
        saldo = 0
        if not df_portafolio.empty and ticker_in in df_portafolio["Ticker"].values:
            saldo = df_portafolio[df_portafolio["Ticker"] == ticker_in]["Cantidad"].sum()
        if tipo == "Venta": st.caption(f"Tienes {saldo} disponibles.")
        
        cant_in = st.number_input("Cantidad", min_value=0.0001, format="%.4f")
        prec_in = st.number_input("Precio ($)", min_value=0.01, format="%.2f")
        fecha_in = st.date_input("Fecha", datetime.now())
        
        if st.form_submit_button("Guardar Operación"):
            if not ticker_in:
                st.warning("Escribe un Ticker.")
            elif tipo == "Venta" and cant_in > saldo:
                st.error("No tienes suficientes acciones.")
            else:
                guardar_operacion(ticker_in, cant_in, prec_in, fecha_in, tipo)
                st.success("Guardado en la nube!")
                st.rerun()

# --- LÓGICA PRINCIPAL ---
if not df_portafolio.empty:
    # 1. Obtener lista única de mis acciones
    mis_tickers = df_portafolio["Ticker"].unique().tolist()
    
    # 2. Buscar precios AUTOMÁTICAMENTE
    precios_live = obtener_precios_actuales(mis_tickers)
    
    # 3. Calcular
    # Agrupamos por ticker para ver totales
    df_resumen = df_portafolio.groupby("Ticker").agg({
        "Cantidad": "sum",
        "Precio": "mean" # Precio promedio de compra (simple)
    }).reset_index()
    
    # OJO: El precio promedio real requiere cálculo ponderado, 
    # aquí hacemos una aproximación simple o calculamos el costo total
    
    # Mejor enfoque: Calcular Costo Total Real
    df_portafolio["Costo Total"] = df_portafolio["Cantidad"] * df_portafolio["Precio"]
    costos_reales = df_portafolio.groupby("Ticker")["Costo Total"].sum().reset_index()
    
    df_final = df_resumen.merge(costos_reales, on="Ticker")
    
    # Mapear precio actual
    df_final["Precio Actual"] = df_final["Ticker"].map(precios_live)
    df_final["Valor Hoy"] = df_final["Cantidad"] * df_final["Precio Actual"]
    df_final["Ganancia $"] = df_final["Valor Hoy"] - df_final["Costo Total"]
    df_final["Rentabilidad %"] = (df_final["Ganancia $"] / df_final["Costo Total"]) * 100
    
    # Limpieza: Quitar acciones que ya vendí todas (Cantidad 0)
    df_final = df_final[df_final["Cantidad"] > 0.00001]

    # --- DASHBOARD ---
    
    # KPIs Globales
    total_inv = df_final["Costo Total"].sum()
    valor_act = df_final["Valor Hoy"].sum()
    ganancia = df_final["Ganancia $"].sum()
    rent_total = (ganancia / total_inv * 100) if total_inv > 0 else 0
    
    st.markdown("### 🏦 Estado de Cuenta (USD)")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Valor Portafolio", f"${valor_act:,.2f}")
    k2.metric("Ganancia Total", f"${ganancia:,.2f}", delta=f"{rent_total:.2f}%")
    k3.metric("Costo Base", f"${total_inv:,.2f}")
    k4.metric("Activos", len(df_final))
    
    # Gráficos
    tab1, tab2 = st.tabs(["📊 Gráficos", "📋 Detalle"])
    
    with tab1:
        c1, c2 = st.columns(2)
        c1.plotly_chart(px.pie(df_final, values="Valor Hoy", names="Ticker", hole=0.4, title="Diversificación"), use_container_width=True)
        c2.plotly_chart(px.bar(df_final, x="Ticker", y="Ganancia $", color="Ganancia $", title="Ganancia por Activo", color_continuous_scale="RdYlGn"), use_container_width=True)
        
    with tab2:
        st.dataframe(df_final.style.format({
            "Cantidad": "{:.4f}",
            "Precio Actual": "${:.2f}",
            "Valor Hoy": "${:.2f}",
            "Ganancia $": "${:.2f}",
            "Rentabilidad %": "{:.2f}%"
        }), use_container_width=True)

else:
    st.info("👈 Registra tu primera acción internacional (Ej: AAPL, SPY) para comenzar.")
