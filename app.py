import streamlit as st
import pandas as pd
import datetime

st.set_page_config(page_title="Gestión Inteligente de Vencimientos - Hospital", page_icon="💊", layout="wide")

st.title("🏥 Panel de Control de Vencimientos y Traspasos - Farmacias Hospitalarias")
st.markdown("Optimización de rotación de fármacos entre Farmacia Activa Urgencia, Atención Abierta y Atención Cerrada (basado en salidas por receta).")

@st.cache_data
def load_data():
    # Load files
    df_stock = pd.read_excel('stocks 8 octubre.xlsx', skiprows=2, names=['Codigo', 'ZGEN', 'Producto', 'Stock_actual', 'Stock_critico', 'Stock_minimo', 'Stock_maximo', 'Precio'])
    df_venc = pd.read_excel('vencimiento 90 dias.xlsx', skiprows=2, names=['Establecimiento', 'Bodega', 'Codigo', 'Producto', 'Lote', 'Fecha_Vencimiento', 'Cantidad', 'Precio_Lote', 'Total'])
    df_salidas = pd.read_excel('Salidas por bodega de abastecimiento.xlsx', skiprows=2, names=['Establecimiento', 'Centro_Costo', 'Bodega_Origen', 'Bodega_Destino', 'Codigo', 'Producto', 'Unidad_Medida', 'Cantidad', 'Total', 'Tipo_Documento'])
    
    target_bodegas = [
        'FARMACIA ACTIVA URGENCIA', 
        'FARMACIA ATENCION ABIERTA', 
        'FARMACIA ATENCION CERRADA - MEDICAMENTOS 1'
    ]
    
    # Filter vencimientos
    df_venc_filtered = df_venc[df_venc['Bodega'].isin(target_bodegas)].copy()
    df_venc_filtered['Cantidad'] = pd.to_numeric(df_venc_filtered['Cantidad'], errors='coerce').fillna(0)
    df_venc_filtered['Fecha_Vencimiento'] = pd.to_datetime(df_venc_filtered['Fecha_Vencimiento'], format='%d/%m/%Y', errors='coerce')
    
    current_date = pd.to_datetime('2026-10-08')
    limit_date = current_date + pd.DateOffset(months=3)
    
    df_venc_90 = df_venc_filtered[(df_venc_filtered['Fecha_Vencimiento'] <= limit_date)].copy()
    df_venc_90['Dias_Para_Vencer'] = (df_venc_90['Fecha_Vencimiento'] - current_date).dt.days
    
    # Filter salidas by receta
    df_salidas_receta = df_salidas[
        (df_salidas['Bodega_Origen'].isin(target_bodegas)) & 
        (df_salidas['Tipo_Documento'] == 'RECETA')
    ].copy()
    df_salidas_receta['Cantidad'] = pd.to_numeric(df_salidas_receta['Cantidad'], errors='coerce').fillna(0)
    
    consumo_mensual = df_salidas_receta.groupby(['Bodega_Origen', 'Codigo', 'Producto'], as_index=False)['Cantidad'].sum()
    consumo_mensual['Consumo_Mensual'] = consumo_mensual['Cantidad'] / 3.0
    
    consumo_pivot = consumo_mensual.pivot_table(index=['Codigo', 'Producto'], columns='Bodega_Origen', values='Consumo_Mensual', fill_value=0).reset_index()
    
    merged_analysis = pd.merge(df_venc_90, consumo_pivot, on=['Codigo', 'Producto'], how='left')
    valid_expiring = merged_analysis[(merged_analysis['Dias_Para_Vencer'] > 0) & (merged_analysis['Dias_Para_Vencer'] <= 90)].copy()
    
    col_map = {
        'FARMACIA ACTIVA URGENCIA': 'FARMACIA ACTIVA URGENCIA',
        'FARMACIA ATENCION ABIERTA': 'FARMACIA ATENCION ABIERTA',
        'FARMACIA ATENCION CERRADA - MEDICAMENTOS 1': 'FARMACIA ATENCION CERRADA - MEDICAMENTOS 1'
    }
    
    def get_recommendation(row):
        current_pharmacy = row['Bodega']
        batch_qty = row['Cantidad']
        days_left = row['Dias_Para_Vencer']
        curr_col = col_map.get(current_pharmacy)
        curr_consumption_monthly = row[curr_col] if curr_col and curr_col in row else 0
        est_consumption_own = (curr_consumption_monthly / 30.0) * days_left
        
        if est_consumption_own >= batch_qty:
            return f"Mantener en {current_pharmacy} (Consumo propio suf.: {est_consumption_own:.1f} vs Lote: {batch_qty})"
        else:
            other_pharmacies = [p for p in col_map.keys() if p != current_pharmacy]
            best_other = None
            max_other_consumption = -1
            for op in other_pharmacies:
                op_val = row.get(op, 0)
                if op_val > max_other_consumption:
                    max_other_consumption = op_val
                    best_other = op
            deficit = batch_qty - est_consumption_own
            if max_other_consumption > 0:
                return f"TRASPARAR a {best_other} (Consumo allí: {max_other_consumption:.1f}/mes)"
            else:
                return f"ALERTA CRÍTICA: Sin consumo registrado en farmacias"

    valid_expiring['Recomendacion'] = valid_expiring.apply(get_recommendation, axis=1)
    return valid_expiring

df_res = load_data()

# Sidebar filters
st.sidebar.header("🔍 Filtros de Visualización")
farmacia_sel = st.sidebar.selectbox("Filtrar por Farmacia Actual:", ["Todas"] + list(df_res['Bodega'].unique()))
max_dias = st.sidebar.slider("Días máximos para vencer:", 30, 90, 90)

df_filtered = df_res[df_res['Dias_Para_Vencer'] <= max_dias]
if farmacia_sel != "Todas":
    df_filtered = df_filtered[df_filtered['Bodega'] == farmacia_sel]

# Metrics
col1, col2, col3 = st.columns(3)
col1.metric("Lotes en Riesgo (<= 90 días)", len(df_res))
col2.metric("Valor Financiero Total en Riesgo", f"${df_res['Total'].sum():,.0f} CLP")
col3.metric("Lotes Filtrados Actuales", len(df_filtered))

st.markdown("---")
st.subheader("📋 Detalle de Lotes y Recomendaciones de Traspaso")

display_cols = ['Bodega', 'Codigo', 'Producto', 'Lote', 'Fecha_Vencimiento', 'Cantidad', 'Total', 'Dias_Para_Vencer', 'Recomendacion']
st.dataframe(df_filtered[display_cols].style.format({'Total': '${:,.0f}', 'Fecha_Vencimiento': lambda x: x.strftime('%d/%m/%Y')}), use_container_width=True)

# Download CSV button
csv = df_filtered[display_cols].to_csv(index=False, encoding='utf-8-sig')
st.download_button(
    label="📥 Descargar Reporte Filtrado en CSV",
    data=csv,
    file_name='reporte_traspasos_streamlit.csv',
    mime='text/csv',
)