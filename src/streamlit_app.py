import streamlit as st
import subprocess
import pandas as pd
from pathlib import Path
import os
import matplotlib.pyplot as plt

st.set_page_config(page_title="Simulador NTN", layout="wide")

st.title("Simulador NTN: Ubicación y Peticiones")

st.sidebar.header("Configuración")
algorithm = st.sidebar.selectbox("Algoritmo de Ubicación", ["Aleatorio (Random)", "Voraz (Greedy)", "Clasificación (Clasification)"])
seed = st.sidebar.number_input("Semilla Aleatoria", value=42, step=1)
requests_per_service = st.sidebar.number_input("Peticiones por servicio/app", value=5, min_value=1, step=1)
congestion_penalty = st.sidebar.number_input("Penalización por Congestión (ms)", value=0.0, min_value=0.0, step=0.5, format="%.1f")

ms_csv_path = Path("data/microservicios_zonificados.csv")
app_csv_path = Path("data/aplicaciones.csv")
if ms_csv_path.exists() and app_csv_path.exists():
    try:
        num_ms = len(pd.read_csv(ms_csv_path))
        num_apps = len(pd.read_csv(app_csv_path))
        total_indiv = num_ms * requests_per_service
        total_app_reqs = num_apps * requests_per_service
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("Resumen de Carga")
        st.sidebar.metric("Total Peticiones a Simular", total_indiv + total_app_reqs)
        st.sidebar.caption(f"- {total_indiv} peticiones individuales ({num_ms} servicios)")
        st.sidebar.caption(f"- {total_app_reqs} peticiones de aplicaciones ({num_apps} apps)")
    except Exception:
        pass

algo_map = {
    "Aleatorio (Random)": ("random_placement.py", "placements_random.csv", "placements_random.png"),
    "Voraz (Greedy)": ("greedy_placement.py", "placements_greedy.csv", "placements_greedy.png"),
    "Clasificación (Clasification)": ("clasification_placement.py", "placements_clasification.csv", "placements_clasification.png")
}

script_name, out_csv, out_png = algo_map[algorithm]

tab1, tab2, tab3, tab4 = st.tabs(["1. Mapa de Red (NTN)", "2. Ubicación (Placements)", "3. Simulación (Requests)", "4. Estudio Comparativo"])

with tab1:
    st.header("Distribución de la Red NTN")
    st.info("Visualiza la distribución física de los drones (UAV) y HAPS sobre el terreno.")
    if st.button("Generar Mapa", type="primary"):
        with st.spinner("Generando mapa de la red..."):
            cmd = ["python", "src/visualizar_ntn.py", "--no-show", "--out", "outputs/visualization.png"]
            result = subprocess.run(cmd, cwd=".", capture_output=True, text=True)
            vis_path = Path("outputs/visualization.png")
            if vis_path.exists():
                st.image(str(vis_path), caption="Distribución de Drones y HAPS")
            else:
                st.error("No se pudo generar el mapa.")

with tab2:
    st.header(f"Ejecutar Algoritmo: {algorithm}")
    if st.button("Ejecutar Asignación", type="primary"):
        with st.spinner("Ejecutando algoritmo de asignación..."):
            result = subprocess.run(["python", f"src/{script_name}", "--seed", str(seed)], cwd=".", capture_output=True, text=True)
            st.success("¡Asignación completada!")
            with st.expander("Ver logs de consola"):
                st.code(result.stdout)
            
            png_path = Path("outputs") / out_png
            if png_path.exists():
                st.image(str(png_path), caption="Distribución de Microservicios por Nodo")
            
            csv_path = Path("outputs") / out_csv
            if csv_path.exists():
                st.subheader("Datos de Asignación")
                df = pd.read_csv(csv_path)
                st.dataframe(df)

with tab3:
    st.header("Simulación de Peticiones y Cadenas")
    st.info("La simulación utilizará las asignaciones generadas por el algoritmo que tengas seleccionado en el panel lateral.")
    if st.button("Ejecutar Simulación", type="primary"):
        csv_path = Path("outputs") / out_csv
        if not csv_path.exists():
            st.error(f"¡Atención! No se encuentra el archivo `{out_csv}`. Por favor, ejecuta primero la asignación en la Pestaña 2.")
        else:
            with st.spinner("Simulando peticiones multisalto..."):
                cmd = ["python", "src/simulate_requests.py", "--seed", str(seed), "--placements", f"outputs/{out_csv}", "--requests-per-service", str(requests_per_service), "--congestion-penalty", str(congestion_penalty)]
                result = subprocess.run(cmd, cwd=".", capture_output=True, text=True)
                st.success("¡Simulación completada!")
                
                with st.expander("Ver logs de consola completos"):
                    st.code(result.stdout)
                    
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Microservicios Individuales")
                    req_csv = Path("outputs/requests_simulation.csv")
                    if req_csv.exists():
                        df_req = pd.read_csv(req_csv)
                        avg_lat = pd.to_numeric(df_req['total_ms'], errors='coerce').mean()
                        slo_viol = len(df_req[df_req['slo_violation'] == 'YES'])
                        
                        m1, m2 = st.columns(2)
                        m1.metric("Latencia Media", f"{avg_lat:.2f} ms")
                        m2.metric("Violaciones SLO", f"{slo_viol} ({slo_viol/len(df_req):.1%})")
                        
                        st.dataframe(df_req)
                
                with col2:
                    st.subheader("Cadenas de Aplicaciones")
                    app_csv = Path("outputs/app_requests_simulation.csv")
                    if app_csv.exists():
                        df_app = pd.read_csv(app_csv)
                        app_avg_lat = pd.to_numeric(df_app['total_ms'], errors='coerce').mean()
                        app_slo_viol = len(df_app[df_app['slo_violation'] == 'YES'])
                        
                        m3, m4 = st.columns(2)
                        m3.metric("Latencia Media App", f"{app_avg_lat:.2f} ms")
                        m4.metric("Violaciones SLO App", f"{app_slo_viol} ({app_slo_viol/len(df_app):.1%})")
                        
                        st.dataframe(df_app)

with tab4:
    st.header("Estudio Comparativo de Algoritmos")
    st.info("Evalúa la evolución de la latencia y las violaciones SLO aumentando progresivamente el volumen de peticiones. Esta simulación ejecuta todos los algoritmos en segundo plano.")
    
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        study_max_req = st.number_input("Peticiones máximas por servicio", value=20, min_value=5, step=5)
    with col_s2:
        study_step = st.number_input("Paso de incremento", value=5, min_value=1, step=1)
    
    if st.button("Ejecutar Estudio de Escalabilidad", type="primary"):
        study_results_indiv = []
        study_results_app = []
        
        algos_to_test = {
            "Aleatorio": ("random_placement.py", "placements_random.csv"),
            "Voraz": ("greedy_placement.py", "placements_greedy.csv"),
            "Clasificación": ("clasification_placement.py", "placements_clasification.csv")
        }
        
        progress_text = "Ejecutando estudio comparativo..."
        my_bar = st.progress(0, text=progress_text)
        
        steps = list(range(study_step, study_max_req + 1, study_step))
        if not steps:
            steps = [study_max_req]
            
        total_iters = len(algos_to_test) * len(steps)
        current_iter = 0
        
        for algo_name, (script, out_csv) in algos_to_test.items():
            # Run placement once for this algorithm
            subprocess.run(["python", f"src/{script}", "--seed", str(seed)], cwd=".", capture_output=True)
            
            for reqs in steps:
                # Run simulation
                cmd = ["python", "src/simulate_requests.py", "--seed", str(seed), "--placements", f"outputs/{out_csv}", "--requests-per-service", str(reqs), "--congestion-penalty", str(congestion_penalty)]
                subprocess.run(cmd, cwd=".", capture_output=True)
                
                # Collect metrics
                req_csv = Path("outputs/requests_simulation.csv")
                app_csv = Path("outputs/app_requests_simulation.csv")
                
                if req_csv.exists():
                    df_req = pd.read_csv(req_csv)
                    avg_lat = pd.to_numeric(df_req['total_ms'], errors='coerce').mean()
                    slo_viol = len(df_req[df_req['slo_violation'] == 'YES'])
                    viol_pct = (slo_viol / len(df_req)) * 100 if len(df_req) > 0 else 0
                    
                    study_results_indiv.append({
                        "Algoritmo": algo_name,
                        "Peticiones por Servicio": reqs,
                        "Latencia Media (ms)": avg_lat,
                        "Violaciones SLO (%)": viol_pct
                    })
                
                if app_csv.exists():
                    df_app = pd.read_csv(app_csv)
                    app_avg_lat = pd.to_numeric(df_app['total_ms'], errors='coerce').mean()
                    app_slo_viol = len(df_app[df_app['slo_violation'] == 'YES'])
                    app_viol_pct = (app_slo_viol / len(df_app)) * 100 if len(df_app) > 0 else 0
                    
                    study_results_app.append({
                        "Algoritmo": algo_name,
                        "Peticiones por Servicio": reqs,
                        "Latencia Media App (ms)": app_avg_lat,
                        "Violaciones SLO App (%)": app_viol_pct
                    })
                
                current_iter += 1
                my_bar.progress(current_iter / total_iters, text=f"Progreso: {algo_name} con {reqs} peticiones ({current_iter}/{total_iters})")
        
        my_bar.empty()
        st.success("¡Estudio completado!")
        
        if study_results_indiv:
            st.subheader("Resultados para Microservicios Individuales")
            df_indiv = pd.DataFrame(study_results_indiv)
            
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("**Evolución de Latencia Media**")
                chart_lat = df_indiv.pivot(index="Peticiones por Servicio", columns="Algoritmo", values="Latencia Media (ms)")
                st.line_chart(chart_lat)
            with col_c2:
                st.markdown("**Evolución de Violaciones SLO (%)**")
                chart_viol = df_indiv.pivot(index="Peticiones por Servicio", columns="Algoritmo", values="Violaciones SLO (%)")
                st.line_chart(chart_viol)
                
        if study_results_app:
            st.subheader("Resultados para Cadenas de Aplicaciones (Multisalto)")
            df_apps = pd.DataFrame(study_results_app)
            
            col_c3, col_c4 = st.columns(2)
            with col_c3:
                st.markdown("**Evolución de Latencia Media App**")
                chart_lat_app = df_apps.pivot(index="Peticiones por Servicio", columns="Algoritmo", values="Latencia Media App (ms)")
                st.line_chart(chart_lat_app)
            with col_c4:
                st.markdown("**Evolución de Violaciones SLO App (%)**")
                chart_viol_app = df_apps.pivot(index="Peticiones por Servicio", columns="Algoritmo", values="Violaciones SLO App (%)")
                st.line_chart(chart_viol_app)
                
        # Generate and save matplotlib plots with white background and axis labels
        if study_results_indiv and study_results_app:
            st.info("Generando gráficos de alta calidad (PNG) para la memoria...")
            import matplotlib.pyplot as plt
            
            out_dir = Path("outputs")
            out_dir.mkdir(exist_ok=True)
            
            # 1. Latencia Individual
            fig, ax = plt.subplots(figsize=(8, 5))
            fig.patch.set_facecolor('white')
            ax.set_facecolor('white')
            for algo in df_indiv['Algoritmo'].unique():
                df_algo = df_indiv[df_indiv['Algoritmo'] == algo]
                ax.plot(df_algo['Peticiones por Servicio'], df_algo['Latencia Media (ms)'], marker='o', label=algo)
            ax.set_xlabel('Peticiones Simultáneas (Carga)')
            ax.set_ylabel('Latencia Media (ms)')
            ax.set_title('Latencia Media - Servicios Individuales')
            ax.legend()
            ax.grid(True, linestyle='--', alpha=0.7)
            fig.savefig(out_dir / 'resultados_latencia_individual.png', dpi=300, bbox_inches='tight', facecolor='white', transparent=False)
            plt.close(fig)
            
            # 2. SLO Individual
            fig, ax = plt.subplots(figsize=(8, 5))
            fig.patch.set_facecolor('white')
            ax.set_facecolor('white')
            for algo in df_indiv['Algoritmo'].unique():
                df_algo = df_indiv[df_indiv['Algoritmo'] == algo]
                ax.plot(df_algo['Peticiones por Servicio'], df_algo['Violaciones SLO (%)'], marker='s', label=algo)
            ax.set_xlabel('Peticiones Simultáneas (Carga)')
            ax.set_ylabel('Violaciones de SLO (%)')
            ax.set_title('Violaciones SLO - Servicios Individuales')
            ax.legend()
            ax.grid(True, linestyle='--', alpha=0.7)
            fig.savefig(out_dir / 'resultados_slo_individual.png', dpi=300, bbox_inches='tight', facecolor='white', transparent=False)
            plt.close(fig)
            
            # 3. Latencia Multisalto
            fig, ax = plt.subplots(figsize=(8, 5))
            fig.patch.set_facecolor('white')
            ax.set_facecolor('white')
            for algo in df_apps['Algoritmo'].unique():
                df_algo = df_apps[df_apps['Algoritmo'] == algo]
                ax.plot(df_algo['Peticiones por Servicio'], df_algo['Latencia Media App (ms)'], marker='^', label=algo)
            ax.set_xlabel('Peticiones Simultáneas (Carga)')
            ax.set_ylabel('Latencia Acumulada (ms)')
            ax.set_title('Latencia Media Acumulada - Service Chaining')
            ax.legend()
            ax.grid(True, linestyle='--', alpha=0.7)
            fig.savefig(out_dir / 'resultados_latencia_multisalto.png', dpi=300, bbox_inches='tight', facecolor='white', transparent=False)
            plt.close(fig)
            
            # 4. SLO Multisalto
            fig, ax = plt.subplots(figsize=(8, 5))
            fig.patch.set_facecolor('white')
            ax.set_facecolor('white')
            for algo in df_apps['Algoritmo'].unique():
                df_algo = df_apps[df_apps['Algoritmo'] == algo]
                ax.plot(df_algo['Peticiones por Servicio'], df_algo['Violaciones SLO App (%)'], marker='d', label=algo)
            ax.set_xlabel('Peticiones Simultáneas (Carga)')
            ax.set_ylabel('Violaciones de SLO Acumuladas (%)')
            ax.set_title('Violaciones SLO - Service Chaining')
            ax.legend()
            ax.grid(True, linestyle='--', alpha=0.7)
            fig.savefig(out_dir / 'resultados_slo_multisalto.png', dpi=300, bbox_inches='tight', facecolor='white', transparent=False)
            plt.close(fig)
            
            st.success("Gráficas guardadas automáticamente en la carpeta `outputs/` con nombres compatibles para la memoria LaTeX.")
