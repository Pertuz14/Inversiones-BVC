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
    """Carga el historial de operaciones."""
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
    """Guarda Compra (Positivo) o Venta (Negativo)."""
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

# --- FUNCIÓN INTELIGENTE DE PRECIOS ---
def limpiar_precio_bvc(valor):
    """
    Arregla el problema de lectura de precios.
    - Si Google manda un número (12.5), lo respeta.
    - Si Google manda texto venezolano (1.200,50), lo convierte.
    """
    if isinstance(valor, (int, float)):
        return float(valor)
    
    texto = str(valor).strip()
    if not texto: return 0.0
    
    try:
        # Intenta formato VE: Quita puntos de mil, cambia coma por punto
        return float(texto.replace('.', '').replace(',', '.'))
    except:
        try:
            # Intento formato estándar
            return float(texto)
        except:
            return 0.0

def cargar_precios_web_full():
    """Lee TODOS los precios disponibles en la hoja."""
    try:
        df_web = conn.read(worksheet="Precios_Web", ttl=0)
        
        if df_web.empty:
            return pd.DataFrame()

        df_web.columns = df_web.columns.str.strip()
        
        # Buscar columna de Ticker
        posibles_tickers = ["símbolo", "simbolo", "ticker", "código", "codigo", "especie"]
        col_ticker = next((c for c in df_web.columns if any(t in c.lower() for t in posibles_tickers)), None)
        if not col_ticker: col_ticker = df_web.columns[0] # Fallback a primera col

        # Buscar columna de Precio
        posibles_precios = ["último", "ultimo", "cierre", "precio", "valor", "cotización"]
        col_precio = next((c for c in df_web.columns if any(p in c.lower() for p in posibles_precios)), None)
        if not col_precio and len(df_web.columns) > 1: col_precio = df_web.columns[1] # Fallback a segunda col

        if col_ticker and col_precio:
            # Creamos diccionario limpio
            precios_dict = {}
            for _, row in df_web.iterrows():
                tick = str(row[col_ticker]).strip().upper()
                precio_sucio = row[col_precio]
                precios_dict[tick] = limpiar_precio_bvc(precio_sucio)
            
            return precios_dict
        else:
            return {}
            
    except Exception as e:
        st.error(f"Error leyendo hoja precios: {e}")
        return {}

# --- INTERFAZ PRINCIPAL ---
st.title("🇻🇪 Mi Portafolio de Inversiones")
st.markdown("---")

# Tasa BCV
tasa_bcv = obtener_tasa_bcv()
tasa_uso = tasa_bcv if tasa_bcv > 0 else st.number_input("⚠️ BCV Caído. Tasa Manual:", value=60.0)

col_tasa, _ = st.columns([1, 4])
if tasa_bcv > 0: col_tasa.metric("Tasa BCV", f"Bs. {tasa_bcv}", delta="En línea")

# Cargar Datos
df_portafolio = cargar_datos()
precios_web_dict = cargar_precios_web_full()

# --- DEFINIR LISTA DE ACCIONES (DINÁMICA) ---
# Unimos las que ya tienes compradas + las que aparecen en la hoja de precios
mis_acciones = df_portafolio["Ticker"].unique().tolist() if not df_portafolio.empty else []
acciones_en_web = list(precios_web_dict.keys())

# Lista maestra para el dropdown (sin duplicados y ordenada)
lista_acciones_completa = sorted(list(set(mis_acciones + acciones_en_web)))
if not lista_acciones_completa:
    lista_acciones_completa = ['BNC', 'MVZ.A', 'TDV.D', 'RST', 'PTN', 'BVL', 'CANTV', 'FVI.B'] # Backup

# --- BARRA LATERAL ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/0/0a/Python.svg/1200px-Python.svg.png", width=50)
    st.header("📝 Operaciones")
    
    tipo_operacion = st.radio("Acción:", ["Compra", "Venta"], horizontal=True)

    with st.form("form_compra"):
        st.info(f"Tasa registro: Bs. {tasa_uso}")
        
        # AQUI ESTA EL CAMBIO: El dropdown ahora tiene TODAS las acciones de la hoja
        ticker_in = st.selectbox("Acción", lista_acciones_completa)
        
        saldo_actual = 0
        if not df_portafolio.empty and ticker_in in df_portafolio["Ticker"].values:
            saldo_actual = df_portafolio[df_portafolio["Ticker"] == ticker_in]["Cantidad"].sum()
        
        if tipo_operacion == "Venta":
            st.caption(f"⚠️ Tienes {saldo_actual} disponibles.")
        
        cant_in = st.number_input("Cantidad", min_value=1, value=100)
        costo_in = st.number_input(f"Precio {tipo_operacion} (Bs)", min_value=0.01, format="%.2f")
        fecha_in = st.date_input("Fecha", datetime.now())
        
        if st.form_submit_button(f"💾 Registrar {tipo_operacion}"):
            if tipo_operacion == "Venta" and cant_in > saldo_actual:
                st.error(f"❌ No tienes suficientes acciones (Tienes {saldo_actual}).")
            else:
                guardar_operacion(ticker_in, cant_in, costo_in, fecha_in, tasa_uso, tipo_operacion)
                st.success("¡Registrado!")
                st.rerun()

# --- SECCIÓN DE PRECIOS ---
# Inicializar estado si está vacío
if 'precios_mercado' not in st.session_state:
    # Por defecto iniciamos con MIS acciones, si no tengo, con todas
    iniciar_con = mis_acciones if mis_acciones else lista_acciones_completa
    st.session_state.precios_mercado = pd.DataFrame({"Ticker": iniciar_con, "Precio Bs.": [0.0]*len(iniciar_con)})

st.subheader("📊 Precios de Hoy")

# Botón Cargar
col_man, col_auto = st.columns([3, 1])
with col_auto:
    st.write("")
    st.write("")
    if st.button("🔄 Cargar de Sheets"):
        if precios_web_dict:
            # Crear DataFrame con TODOS los precios encontrados
            # Pero filtrar segun lo que el usuario quiera ver abajo
            df_update = pd.DataFrame(list(precios_web_dict.items()), columns=["Ticker", "Precio Bs."])
            st.session_state.precios_mercado = df_update
            st.success(f"¡Precios actualizados ({len(df_update)} acciones)!")
            st.rerun()
        else:
            st.warning("Hoja vacía o sin datos reconocibles.")

# Tabla Editable
with col_man:
    # FILTRO: ¿Mostrar todo o solo lo mio?
    mostrar_todas = st.checkbox("Ver todas las acciones disponibles (Web)", value=False)
    
    df_visual = st.session_state.precios_mercado.copy()
    
    # Si NO quiere ver todas, filtramos solo por las que tiene en portafolio
    if not mostrar_todas and mis_acciones:
        df_visual = df_visual[df_visual["Ticker"].isin(mis_acciones)]
    
    with st.expander("📝 Tabla de Precios (Editable)", expanded=True):
        df_editado = st.data_editor(
            df_visual,
            column_config={"Precio Bs.": st.column_config.NumberColumn(format="%.2f Bs")},
            hide_index=True,
            use_container_width=True,
            key="editor_precios"
        )
        # Actualizamos el estado global solo con las filas que se editaron
        # (Esto es un truco para mantener sincronizado el filtro)
        if not df_editado.equals(df_visual):
             # Actualizar en el maestro solo las que cambiaron
             for i, row in df_editado.iterrows():
                 idx_master = st.session_state.precios_mercado.index[st.session_state.precios_mercado["Ticker"] == row["Ticker"]]
                 if not idx_master.empty:
                     st.session_state.precios_mercado.at[idx_master[0], "Precio Bs."] = row["Precio Bs."]


# --- CÁLCULOS Y KPIs ---
if not df_portafolio.empty:
    # Usamos el DF maestro de precios para los cálculos (no el filtrado visual)
    df_final = df_portafolio.merge(st.session_state.precios_mercado, on="Ticker", how="left")
    
    df_final["Inv. Total (Bs)"] = df_final["Total Invertido (Bs)"]
    # Si no hay precio actual, asume 0
    df_final["Precio Bs."] = df_final["Precio Bs."].fillna(0)
    
    df_final["Valor Hoy (Bs)"] = df_final["Cantidad"] * df_final["Precio Bs."]
    df_final["Ganancia (Bs)"] = df_final["Valor Hoy (Bs)"] - df_final["Inv. Total (Bs)"]
    
    df_final["Valor Hoy ($)"] = df_final["Valor Hoy (Bs)"] / tasa_uso
    df_final["Inv. Total ($)"] = df_final["Total Invertido ($)"]
    df_final["Ganancia ($)"] = df_final["Valor Hoy ($)"] - df_final["Inv. Total ($)"]
    
    df_final["Rentabilidad %"] = df_final.apply(
        lambda x: (x["Ganancia ($)"] / x["Inv. Total ($)"] * 100) if x["Inv. Total ($)"] != 0 else 0, axis=1
    )

    # --- KPIs ---
    st.markdown("### 💰 Estado de Cuenta")
    
    total_usd = df_final["Valor Hoy ($)"].sum()
    ganancia_usd = df_final["Ganancia ($)"].sum()
    inv_total_usd = df_final["Inv. Total ($)"].sum()
    
    total_bs = df_final["Valor Hoy (Bs)"].sum()
    ganancia_bs = df_final["Ganancia (Bs)"].sum()
    inv_total_bs = df_final["Inv. Total (Bs)"].sum()
    
    rent_total = ((total_usd - inv_total_usd) / inv_total_usd * 100) if inv_total_usd != 0 else 0
    
    # DÓLARES
    st.markdown("##### 💵 Referencia en Divisas")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Valor Cartera ($)", f"${total_usd:,.2f}")
    k2.metric("Ganancia Neta ($)", f"${ganancia_usd:,.2f}", delta_color="normal")
    k3.metric("Total Invertido ($)", f"${inv_total_usd:,.2f}")
    k4.metric("Rentabilidad Global", f"{rent_total:.2f}%")

    # BOLÍVARES
    st.markdown("##### 🇻🇪 Referencia en Bolívares")
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Valor Cartera (Bs)", f"Bs. {total_bs:,.2f}")
    b2.metric("Ganancia Neta (Bs)", f"Bs. {ganancia_bs:,.2f}", delta_color="normal")
    b3.metric("Total Invertido (Bs)", f"Bs. {inv_total_bs:,.2f}")
    b4.empty()
    
    # --- GRÁFICOS ---
    tab1, tab2 = st.tabs(["📈 Distribución & Valor", "📋 Detalle Tabla"])
    
    # Filtramos para gráficos (solo positivos para pie chart)
    df_pos = df_final.groupby("Ticker")[["Valor Hoy ($)", "Ganancia ($)"]].sum().reset_index()
    df_pos = df_pos[df_pos["Valor Hoy ($)"] > 0.01] 

    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            if not df_pos.empty:
                fig_pie = px.pie(df_pos, values='Valor Hoy ($)', names='Ticker', hole=0.4, title="¿Dónde está mi dinero?")
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("No tienes valor positivo actual.")
        with c2:
            fig_bar = px.bar(df_final, x='Ticker', y='Ganancia ($)', color='Ganancia ($)', 
                             title="Rendimiento por Acción ($)", color_continuous_scale="RdBu")
            st.plotly_chart(fig_bar, use_container_width=True)

    with tab2:
        cols = ["Tipo", "Ticker", "Cantidad", "Fecha Compra", "Precio Operacion (Bs)", "Valor Hoy ($)", "Ganancia ($)", "Rentabilidad %"]
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
    
    df_rep = df_final[df_final["Fecha Compra"] >= fecha_corte]
    if not df_rep.empty:
        st.dataframe(df_rep)
    else:
        st.caption("No hay datos en este periodo.")

else:
    st.info("👈 Registra tu primera compra para empezar.")
