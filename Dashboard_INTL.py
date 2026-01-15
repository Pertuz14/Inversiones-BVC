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

# --- FUNCIONES DE DATOS BLINDADAS ---
def cargar_datos():
    try:
        # 1. Leemos la hoja
        df = conn.read(worksheet="Portafolio_INTL", ttl=0)
        
        # 2. LIMPIEZA CRÍTICA: Eliminar filas que estén completamente vacías
        df = df.dropna(how='all')
        
        # 3. Conversión de Fecha (Con corrección de errores)
        if "Fecha" in df.columns:
            # 'coerce' transforma fechas inválidas en NaT (Not a Time) en lugar de dar error
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors='coerce')
            # Eliminamos filas donde la fecha no se pudo leer (basura)
            df = df.dropna(subset=["Fecha"])
            
        return df
    except Exception as e:
        # Si falla, devolvemos DataFrame vacío pero con las columnas correctas
        return pd.DataFrame(columns=["Ticker", "Cantidad", "Precio", "Fecha", "Tipo", "Tasa"])

def obtener_precios_actuales(lista_tickers):
    if not lista_tickers: return {}
    try:
        # Descargamos precios de hoy
        datos = yf.download(lista_tickers, period="1d", progress=False)['Close']
        precios = {}
        
        # Si es una sola acción
        if len(lista_tickers) == 1:
            val = datos.iloc[-1]
            precios[lista_tickers[0]] = float(val)
        else:
            # Si son varias
            current = datos.iloc[-1]
            for tick in lista_tickers:
                if tick in current: precios[tick] = float(current[tick])
        return precios
    except:
        return {}

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
        
        if df_actual.empty:
            df_updated = nuevo
        else:
            # Asegurar columna Tasa
            if "Tasa" not in df_actual.columns:
                df_actual["Tasa"] = 0.0
            
            # Concatenar
            df_updated = pd.concat([df_actual, nuevo], ignore_index=True)
        
        # 4. FORMATEO SEGURO DE FECHA (Para evitar errores al guardar)
        # Aseguramos que TODO sea datetime antes de convertir a string
        df_updated["Fecha"] = pd.to_datetime(df_updated["Fecha"])
        df_updated["Fecha"] = df_updated["Fecha"].dt.strftime('%Y-%m-%d')
        
        # Guardado
        conn.update(worksheet="Portafolio_INTL", data=df_updated)
        st.cache_data.clear()
        return True, "Éxito"
        
    except Exception as e:
        return False, str(e)

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

# --- TAB 1: PORTAFOLIO (ESTILO VISUAL PRO) ---
    with t1:
        st.markdown("### 💰 Estado de Cuenta")
        
        # --- SECCIÓN DÓLARES ---
        st.markdown("##### 💵 Referencia en Divisas")
        
        # Cálculos de Totales
        total_usd = df_final["Valor Hoy $"].sum()
        ganancia_usd = df_final["Ganancia $"].sum()
        invertido_usd = df_final["Costo Total $"].sum()
        rentabilidad_total = (ganancia_usd / invertido_usd * 100) if invertido_usd != 0 else 0
        
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Valor Cartera ($)", f"${total_usd:,.2f}")
        k2.metric("Ganancia Neta ($)", f"${ganancia_usd:,.2f}", delta=f"{rentabilidad_total:.2f}%")
        k3.metric("Total Invertido ($)", f"${invertido_usd:,.2f}")
        k4.metric("Rentabilidad", f"{rentabilidad_total:.2f}%")
        
        # --- SECCIÓN BOLÍVARES ---
        st.markdown("##### 🇻🇪 Referencia en Bolívares")
        
        # Cálculos de Totales Bs
        total_bs = df_final["Valor Hoy Bs"].sum()
        ganancia_bs = df_final["Ganancia Bs"].sum()
        invertido_bs = df_final["Costo Total Bs"].sum()
        
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Valor Cartera (Bs)", f"Bs. {total_bs:,.2f}")
        b2.metric("Ganancia Neta (Bs)", f"Bs. {ganancia_bs:,.2f}", delta_color="normal")
        b3.metric("Total Invertido (Bs)", f"Bs. {invertido_bs:,.2f}")
        b4.write("") # Espacio vacío para mantener alineación
        
        # --- PESTAÑAS INTERNAS DE GRÁFICOS ---
        st.divider()
        subtab_graficos, subtab_detalle = st.tabs(["📈 Distribución", "📋 Detalle"])
        
        with subtab_graficos:
            col_pie, col_bar = st.columns(2)
            
            # Gráfico de Torta (Donut)
            if total_usd > 0:
                fig_pie = px.pie(df_final, values='Valor Hoy $', names='Ticker', hole=0.4)
                fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0))
                col_pie.plotly_chart(fig_pie, use_container_width=True)
            else:
                col_pie.info("Sin datos para graficar.")
            
            # Gráfico de Barras (Ganancias)
            fig_bar = px.bar(df_final, x='Ticker', y='Ganancia $', color='Ganancia $', color_continuous_scale="RdBu")
            fig_bar.update_layout(margin=dict(t=0, b=0, l=0, r=0))
            col_bar.plotly_chart(fig_bar, use_container_width=True)
            
        with subtab_detalle:
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
        st.subheader("📅 Análisis de Rendimiento Histórico")
        
        # 1. Filtro de Tiempo
        periodo_selec = st.selectbox("Seleccionar Plazo:", ["Todo el Historial", "Última Semana", "Último Mes", "Este Año"])
        
        # 2. Filtrar Datos por Fecha
        df_hist = df_portafolio.copy()
        hoy = datetime.now()
        
        if periodo_selec == "Última Semana": fecha_inicio = hoy - timedelta(days=7)
        elif periodo_selec == "Último Mes": fecha_inicio = hoy - timedelta(days=30)
        elif periodo_selec == "Este Año": fecha_inicio = datetime(hoy.year, 1, 1)
        else: fecha_inicio = datetime(2000, 1, 1)
            
        df_filtrado = df_hist[df_hist["Fecha"] >= fecha_inicio]
        
        if not df_filtrado.empty:
            # Separamos las COMPRAS para ver rendimiento de la inversión nueva
            df_compras = df_filtrado[df_filtrado["Tipo"] == "Compra"].copy()
            
            if not df_compras.empty:
                # --- CÁLCULOS FINANCIEROS ---
                
                # A. Lo que gastaste (Invertido)
                # Costo Bs usa la Tasa Histórica (la del día que compraste)
                invertido_usd = df_compras["Costo Total $"].sum()
                invertido_bs = df_compras["Costo Total Bs"].sum() 
                
                # B. Lo que vale AHORA eso que compraste
                # Buscamos precio fresco para estas acciones específicas
                tickers_periodo = df_compras["Ticker"].unique().tolist()
                precios_reporte = obtener_precios_actuales(tickers_periodo)
                
                df_compras["Precio Actual"] = df_compras["Ticker"].map(precios_reporte).fillna(0)
                
                # Valor Hoy $ = Cantidad Comprada * Precio Actual
                df_compras["Valor Hoy $"] = df_compras["Cantidad"] * df_compras["Precio Actual"]
                
                # Valor Hoy Bs = Valor Hoy $ * Tasa HOY (porque si vendes hoy, recibes tasa actual)
                df_compras["Valor Hoy Bs"] = df_compras["Valor Hoy $"] * tasa_hoy
                
                valor_hoy_usd = df_compras["Valor Hoy $"].sum()
                valor_hoy_bs = df_compras["Valor Hoy Bs"].sum()
                
                # C. Ganancias (Valor Hoy - Costo Viejo)
                ganancia_usd = valor_hoy_usd - invertido_usd
                ganancia_bs = valor_hoy_bs - invertido_bs
                
                # D. Rentabilidad %
                rentabilidad = (ganancia_usd / invertido_usd * 100) if invertido_usd > 0 else 0
                
                # --- VISUALIZACIÓN DE MÉTRICAS ---
                st.markdown(f"##### 📊 Rendimiento de compras: {periodo_selec}")
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Invertido ($)", f"${invertido_usd:,.2f}")
                col2.metric("Ganancia ($)", f"${ganancia_usd:,.2f}", delta=f"{rentabilidad:.2f}%")
                col3.metric("Ganancia (Bs)", f"Bs. {ganancia_bs:,.2f}", delta="Vs. Costo Histórico")
                col4.metric("Rentabilidad", f"{rentabilidad:.2f}%")
                
                st.divider()
            else:
                st.info(f"No realizaste nuevas compras en {periodo_selec} (solo ventas o inactividad).")
            
            # Tabla de Movimientos
            st.write("📜 **Detalle de Movimientos**")
            st.dataframe(df_filtrado.sort_values("Fecha", ascending=False)[[
                "Fecha", "Ticker", "Tipo", "Cantidad", "Precio", "Tasa", "Costo Total $"
            ]].style.format({
                "Precio": "${:.2f}",
                "Tasa": "Bs.{:.2f}",
                "Costo Total $": "${:.2f}",
                "Fecha": "{:%Y-%m-%d}"
            }), use_container_width=True)
            
        else:
            st.warning("No hay registros en este periodo.")
else:
    st.info("👈 Registra tu primera operación.")
