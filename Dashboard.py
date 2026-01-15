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

# --- ROBOT BCV ---
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

# ==========================================
#    ⬇️ NUEVAS FUNCIONES DE BITÁCORA ⬇️
# ==========================================

def actualizar_bitacora_tasas(tasa_actual):
    """Guarda la tasa de HOY en la hoja 'Historial_Tasas'."""
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
    except: pass

def buscar_tasa_en_bitacora(fecha_buscada):
    """Busca si tenemos guardada la tasa de una fecha específica."""
    try:
        df_hist = conn.read(worksheet="Historial_Tasas", ttl=600)
        df_hist["Fecha"] = pd.to_datetime(df_hist["Fecha"]).dt.date
        fila = df_hist[df_hist["Fecha"] == fecha_buscada]
        if not fila.empty: return float(fila.iloc[0]["Tasa"])
    except: pass
    return None

# ==========================================
#    ⬆️ FIN DE NUEVAS FUNCIONES ⬆️
# ==========================================

def cargar_datos():
    try:
        df_port = conn.read(worksheet="Portafolio", ttl=0)
        df_port["Fecha Compra"] = pd.to_datetime(df_port["Fecha Compra"])
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
    try:
        df_actual = cargar_datos()
        
        cantidad_final = cantidad
        if tipo == "Venta":
            cantidad_final = -cantidad 
        
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
            "Tipo": tipo
        }])
        
        if df_actual.empty:
            df_actualizado = nuevo_registro
        else:
            df_actualizado = pd.concat([df_actual, nuevo_registro], ignore_index=True)
            
        df_actualizado["Fecha Compra"] = df_actualizado["Fecha Compra"].dt.strftime('%Y-%m-%d')
        conn.update(worksheet="Portafolio", data=df_actualizado)
        st.cache_data.clear()
        return True
    except Exception as e:
        return False

# --- FUNCIONES DE PRECIOS MEJORADAS (Mantenemos tu lógica v5.0) ---
def limpiar_precio_bvc(valor):
    if isinstance(valor, (int, float)): return float(valor)
    texto = str(valor).strip()
    if not texto: return 0.0
    try: return float(texto.replace('.', '').replace(',', '.'))
    except: return 0.0

def cargar_precios_web_full():
    try:
        df_web = conn.read(worksheet="Precios_Web", ttl=0)
        if df_web.empty: return {}
        df_web.columns = df_web.columns.str.strip()
        
        col_ticker = next((c for c in df_web.columns if any(t in c.lower() for t in ["símbolo", "simbolo", "ticker"])), None)
        if not col_ticker: col_ticker = df_web.columns[1] if len(df_web.columns) > 1 else df_web.columns[0]

        col_precio = next((c for c in df_web.columns if any(p in c.lower() for p in ["último", "precio", "valor"])), None)
        if not col_precio and len(df_web.columns) > 2: col_precio = df_web.columns[2]

        if col_ticker and col_precio:
            dict_precios = {}
            for _, row in df_web.iterrows():
                tick = str(row[col_ticker]).strip().upper()
                precio = limpiar_precio_bvc(row[col_precio])
                if tick and tick != "NAN" and precio > 0:
                    dict_precios[tick] = precio
            return dict_precios
        return {}
    except: return {}

# --- INTERFAZ PRINCIPAL ---
st.title("🇻🇪 Mi Portafolio de Inversiones")
st.markdown("---")

# 1. Tasa y Bitácora
tasa_bcv = obtener_tasa_bcv()
tasa_uso_hoy = tasa_bcv if tasa_bcv > 0 else 60.0

# GUARDAMOS LA TASA DE HOY EN LA MEMORIA
actualizar_bitacora_tasas(tasa_uso_hoy)

col_tasa, _ = st.columns([1, 4])
if tasa_bcv > 0: col_tasa.metric("Tasa BCV", f"Bs. {tasa_bcv}")
else: col_tasa.warning("BCV Offline")

df_portafolio = cargar_datos()
precios_web_dict = cargar_precios_web_full()

# --- LISTA DINÁMICA ---
mis_acciones = df_portafolio["Ticker"].unique().tolist() if not df_portafolio.empty else []
acciones_disponibles = sorted(list(set(mis_acciones + list(precios_web_dict.keys()))))
if not acciones_disponibles: acciones_disponibles = ['BNC', 'MVZ.A', 'TDV.D']

# --- BARRA LATERAL INTELIGENTE ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/0/0a/Python.svg/1200px-Python.svg.png", width=50)
    st.header("📝 Registrar Operación")
    
    # FECHA FUERA DEL FORMULARIO
    st.write("📅 **Fecha de la Operación**")
    fecha_in = st.date_input("Selecciona fecha:", datetime.now(), label_visibility="collapsed")
    
    # LÓGICA INTELIGENTE
    tasa_guardada = buscar_tasa_en_bitacora(fecha_in)
    
    if tasa_guardada:
        val_defecto = tasa_guardada
        msg = "✅ Tasa recuperada del historial."
        st.success(f"Tasa encontrada: {tasa_guardada} Bs/$")
    elif fecha_in == datetime.now().date():
        val_defecto = tasa_uso_hoy
        msg = "✅ Tasa actual del BCV."
    else:
        val_defecto = tasa_uso_hoy
        msg = "⚠️ No hay registro. Usa la de hoy o ajusta."
        st.info("Sin datos históricos. Ingresa tasa manual.")

    with st.form("form_compra"):
        st.write("---")
        tipo_operacion = st.radio("Acción:", ["Compra", "Venta"], horizontal=True)
        ticker_in = st.selectbox("Acción", acciones_disponibles)
        
        saldo_actual = 0
        if not df_portafolio.empty and ticker_in in df_portafolio["Ticker"].values:
            saldo_actual = df_portafolio[df_portafolio["Ticker"] == ticker_in]["Cantidad"].sum()
        
        if tipo_operacion == "Venta": st.caption(f"Disponible: {saldo_actual}")
        
        cant_in = st.number_input("Cantidad", 1, 10000000)
        costo_in = st.number_input(f"Precio {tipo_operacion} (Bs)", 0.01, format="%.2f")
        
        # CAMPO DE TASA AUTOMÁTICO
        tasa_in = st.number_input("Tasa Referencia (Bs/$)", min_value=0.1, value=float(val_defecto), format="%.2f", help=msg)
        
        submitted = st.form_submit_button(f"💾 Registrar {tipo_operacion}")
        
        if submitted:
            if tipo_operacion == "Venta" and cant_in > saldo_actual:
                st.error("No tienes suficientes acciones.")
            else:
                with st.spinner("Guardando..."):
                    if guardar_operacion(ticker_in, cant_in, costo_in, fecha_in, tasa_in, tipo_operacion):
                        st.success("Registrado!")
                        st.rerun()
                    else:
                        st.error("Error al guardar en Sheets.")

# --- SECCIÓN DE PRECIOS ---
if 'precios_mercado' not in st.session_state:
    st.session_state.precios_mercado = pd.DataFrame({"Ticker": acciones_disponibles, "Precio Bs.": [0.0]*len(acciones_disponibles)})

st.subheader("📊 Precios de Hoy")

col_man, col_auto = st.columns([3, 1])
with col_auto:
    st.write("")
    st.write("")
    if st.button("🔄 Cargar de Sheets"):
        if precios_web_dict:
            df_nuevo = pd.DataFrame(list(precios_web_dict.items()), columns=["Ticker", "Precio Bs."])
            st.session_state.precios_mercado = df_nuevo
            st.success(f"¡Actualizados {len(df_nuevo)} precios!")
            st.rerun()
        else:
            st.warning("Hoja vacía o sin datos.")

with col_man:
    ver_todo = st.checkbox("Ver todo el mercado", value=False)
    df_visual = st.session_state.precios_mercado.copy()
    if not ver_todo and mis_acciones:
        df_visual = df_visual[df_visual["Ticker"].isin(mis_acciones)]
        
    with st.expander("📝 Tabla de Precios (Editable)", expanded=True):
        df_editado = st.data_editor(
            df_visual,
            column_config={"Precio Bs.": st.column_config.NumberColumn(format="%.2f Bs")},
            hide_index=True,
            use_container_width=True
        )
        if not df_editado.equals(df_visual):
             for i, row in df_editado.iterrows():
                 idx = st.session_state.precios_mercado.index[st.session_state.precios_mercado["Ticker"] == row["Ticker"]]
                 if not idx.empty: st.session_state.precios_mercado.at[idx[0], "Precio Bs."] = row["Precio Bs."]

# --- CÁLCULOS Y KPIs ---
if not df_portafolio.empty:
    df_final = df_portafolio.merge(st.session_state.precios_mercado, on="Ticker", how="left")
    
    df_final["Inv. Total (Bs)"] = df_final["Total Invertido (Bs)"]
    df_final["Precio Bs."] = df_final["Precio Bs."].fillna(0)
    
    df_final["Valor Hoy (Bs)"] = df_final["Cantidad"] * df_final["Precio Bs."]
    df_final["Ganancia (Bs)"] = df_final["Valor Hoy (Bs)"] - df_final["Inv. Total (Bs)"]
    
    # Conversión a dólares usando la TASA ACTUAL (del día)
    df_final["Valor Hoy ($)"] = df_final["Valor Hoy (Bs)"] / tasa_uso_hoy
    df_final["Inv. Total ($)"] = df_final["Total Invertido ($)"]
    df_final["Ganancia ($)"] = df_final["Valor Hoy ($)"] - df_final["Inv. Total ($)"]
    
    # --- KPIs ---
    st.markdown("### 💰 Estado de Cuenta")
    
    total_usd = df_final["Valor Hoy ($)"].sum()
    gan_usd = df_final["Ganancia ($)"].sum()
    inv_usd = df_final["Inv. Total ($)"].sum()
    
    total_bs = df_final["Valor Hoy (Bs)"].sum()
    gan_bs = df_final["Ganancia (Bs)"].sum()
    inv_bs = df_final["Inv. Total (Bs)"].sum()
    
    rent = ((total_usd - inv_usd) / inv_usd * 100) if inv_usd != 0 else 0
    
    st.markdown("##### 💵 Referencia en Divisas")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Valor Cartera ($)", f"${total_usd:,.2f}")
    k2.metric("Ganancia Neta ($)", f"${gan_usd:,.2f}", delta_color="normal")
    k3.metric("Total Invertido ($)", f"${inv_usd:,.2f}")
    k4.metric("Rentabilidad", f"{rent:.2f}%")

    st.markdown("##### 🇻🇪 Referencia en Bolívares")
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Valor Cartera (Bs)", f"Bs. {total_bs:,.2f}")
    b2.metric("Ganancia Neta (Bs)", f"Bs. {gan_bs:,.2f}", delta_color="normal")
    b3.metric("Total Invertido (Bs)", f"Bs. {inv_bs:,.2f}")
    b4.empty()
    
    # --- GRÁFICOS ---
    tab1, tab2 = st.tabs(["📈 Distribución", "📋 Detalle"])
    
    df_pos = df_final.groupby("Ticker")[["Valor Hoy ($)", "Ganancia ($)"]].sum().reset_index()
    df_pos = df_pos[df_pos["Valor Hoy ($)"] > 0.01] 

    with tab1:
        c1, c2 = st.columns(2)
        if not df_pos.empty:
            c1.plotly_chart(px.pie(df_pos, values='Valor Hoy ($)', names='Ticker', hole=0.4), use_container_width=True)
        else: c1.info("Sin valor positivo.")
        c2.plotly_chart(px.bar(df_final, x='Ticker', y='Ganancia ($)', color='Ganancia ($)', color_continuous_scale="RdBu"), use_container_width=True)

    with tab2:
        cols = ["Tipo", "Ticker", "Cantidad", "Fecha Compra", "Precio Operacion (Bs)", "Valor Hoy ($)", "Ganancia ($)", "Rentabilidad %"]
        # Calcular rentabilidad para la tabla
        df_final["Rentabilidad %"] = df_final.apply(lambda x: (x["Ganancia ($)"] / x["Inv. Total ($)"] * 100) if x["Inv. Total ($)"] != 0 else 0, axis=1)
        
        st.dataframe(df_final[cols].style.format({
            "Precio Operacion (Bs)": "{:.2f}",
            "Valor Hoy ($)": "${:.2f}",
            "Ganancia ($)": "${:.2f}",
            "Rentabilidad %": "{:.2f}%"
        }), use_container_width=True)
        
    # --- REPORTES ---
    st.markdown("---")
    st.subheader("📅 Reportes Históricos")
    periodo = st.selectbox("Periodo:", ["Todo", "7 días", "30 días", "365 días"])
    dias = {"Todo": 9999, "7 días": 7, "30 días": 30, "365 días": 365}
    fecha_corte = datetime.now() - timedelta(days=dias[periodo])
    st.dataframe(df_final[df_final["Fecha Compra"] >= fecha_corte])

else:
    st.info("👈 Registra tu primera compra.")
