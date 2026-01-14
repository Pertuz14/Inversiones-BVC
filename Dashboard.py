import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Mi Portafolio BVC", layout="wide")

# --- 1. INICIALIZAR DATOS (Si es la primera vez que abres) ---
if 'portafolio' not in st.session_state:
    # Aquí guardamos tus compras
    st.session_state.portafolio = pd.DataFrame(columns=["Ticker", "Cantidad", "Costo Promedio", "Fecha Compra"])

if 'precios_mercado' not in st.session_state:
    # Aquí están los precios que tú actualizarás manualmente
    data_inicial = {
        "Ticker": ['BNC', 'MVZ.A', 'TDV.D', 'RST', 'PTN', 'BVL', 'CANTV'],
        "Precio Hoy (VES)": [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00]
    }
    st.session_state.precios_mercado = pd.DataFrame(data_inicial)

# --- 2. BARRA LATERAL: REGISTRAR COMPRAS ---
with st.sidebar:
    st.header("💰 Registrar Nueva Inversión")
    ticker_input = st.selectbox("Acción", st.session_state.precios_mercado["Ticker"])
    cantidad_input = st.number_input("Cantidad", min_value=1, value=100)
    costo_input = st.number_input("Costo de Compra (VES)", min_value=0.01, format="%.2f")
    fecha_input = st.date_input("Fecha de Compra", datetime.now())
    
    if st.button("Guardar Compra"):
        nuevo_registro = pd.DataFrame([{
            "Ticker": ticker_input, 
            "Cantidad": cantidad_input, 
            "Costo Promedio": costo_input,
            "Fecha Compra": pd.to_datetime(fecha_input)
        }])
        st.session_state.portafolio = pd.concat([st.session_state.portafolio, nuevo_registro], ignore_index=True)
        st.success(f"¡Compraste {cantidad_input} de {ticker_input}!")

# --- 3. SECCIÓN PRINCIPAL: ACTUALIZAR PRECIOS ---
st.title("🇻🇪 Control de Inversiones - Bolsa de Caracas")

st.info("👇 **PASO 1:** Actualiza aquí los precios del día (haz doble click en la celda 'Precio Hoy')")

# Editor de datos (Interactividad tipo Excel)
df_precios_editado = st.data_editor(
    st.session_state.precios_mercado, 
    num_rows="dynamic", 
    key="editor_precios",
    column_config={
        "Precio Hoy (VES)": st.column_config.NumberColumn(format="%.2f VES")
    }
)

# Guardar los cambios en los precios
st.session_state.precios_mercado = df_precios_editado

# --- 4. CÁLCULOS AUTOMÁTICOS ---
df_port = st.session_state.portafolio

if not df_port.empty:
    # Unir tus compras con los precios que acabas de poner
    df_final = df_port.merge(df_precios_editado, on="Ticker", how="left")
    
    # Matemáticas
    df_final["Inversión Total"] = df_final["Cantidad"] * df_final["Costo Promedio"]
    df_final["Valor Actual"] = df_final["Cantidad"] * df_final["Precio Hoy (VES)"]
    df_final["Ganancia/Pérdida (VES)"] = df_final["Valor Actual"] - df_final["Inversión Total"]
    
    # Evitar división por cero
    df_final["Rendimiento %"] = df_final.apply(
        lambda x: (x["Ganancia/Pérdida (VES)"] / x["Inversión Total"] * 100) if x["Inversión Total"] > 0 else 0, axis=1
    )

    # --- 5. DASHBOARD DE RESULTADOS ---
    st.markdown("---")
    st.subheader("📊 Tu Resumen Financiero")

    total_inv = df_final["Inversión Total"].sum()
    total_act = df_final["Valor Actual"].sum()
    pnl = total_act - total_inv
    
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Dinero Invertido", f"{total_inv:,.2f} VES")
    kpi2.metric("Valor Actual de Cartera", f"{total_act:,.2f} VES")
    kpi3.metric("Ganancia/Pérdida Total", f"{pnl:,.2f} VES", delta_color="normal")

    # Gráficos
    g1, g2 = st.columns(2)
    with g1:
        fig = px.pie(df_final, values='Valor Actual', names='Ticker', title='¿Dónde está tu dinero?')
        st.plotly_chart(fig, use_container_width=True)
    with g2:
        fig2 = px.bar(df_final, x='Ticker', y='Ganancia/Pérdida (VES)', title='Ganancia por Acción', color='Ganancia/Pérdida (VES)')
        st.plotly_chart(fig2, use_container_width=True)

    # --- 6. REPORTES POR PERIODO ---
    st.markdown("---")
    st.subheader("📅 Generar Reportes")
    
    tipo_reporte = st.selectbox("Selecciona Periodo:", ["Todo el Historial", "Esta Semana", "Este Mes", "Este Año"])
    
    hoy = pd.to_datetime(datetime.now())
    df_final["Fecha Compra"] = pd.to_datetime(df_final["Fecha Compra"]) # Asegurar formato fecha
    
    if tipo_reporte == "Esta Semana":
        filtro = df_final[df_final["Fecha Compra"] >= (hoy - timedelta(days=7))]
    elif tipo_reporte == "Este Mes":
        filtro = df_final[df_final["Fecha Compra"] >= (hoy - timedelta(days=30))]
    elif tipo_reporte == "Este Año":
        filtro = df_final[df_final["Fecha Compra"] >= (hoy - timedelta(days=365))]
    else:
        filtro = df_final

    st.write(f"Mostrando rendimiento de inversiones realizadas en: **{tipo_reporte}**")
    st.dataframe(filtro.style.format({
        "Inversión Total": "{:.2f}",
        "Valor Actual": "{:.2f}",
        "Ganancia/Pérdida (VES)": "{:.2f}",
        "Rendimiento %": "{:.2f}%"
    }))

else:
    st.warning("👈 ¡Empieza registrando una compra en el menú de la izquierda!")
       

  

  
        
