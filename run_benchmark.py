import os
import subprocess
import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt

def run_benchmark():
    seed = 42
    congestion_penalty = 2.0
    study_max_req = 300
    study_step = 5
    
    # Exact params from TFG
    steps = list(range(5, 301, 5))
    
    algos_to_test = {
        "Aleatorio": ("random_placement.py", "placements_random.csv"),
        "Voraz": ("greedy_placement.py", "placements_greedy.csv"),
        "Clasificación": ("clasification_placement.py", "placements_clasification.csv")
    }
    
    study_results_indiv = []
    study_results_app = []
    
    # make sure outputs dir exists
    out_dir = Path("outputs")
    out_dir.mkdir(exist_ok=True)
    
    for algo_name, (script, out_csv) in algos_to_test.items():
        print(f"Running placement for {algo_name}...")
        subprocess.run(["python", f"src/{script}", "--seed", str(seed)], cwd=".")
        
        for reqs in steps:
            print(f"  Simulating {reqs} requests/service for {algo_name}...")
            cmd = ["python", "src/simulate_requests.py", "--seed", str(seed), 
                   "--placements", f"outputs/{out_csv}", 
                   "--requests-per-service", str(reqs), 
                   "--congestion-penalty", str(congestion_penalty)]
            subprocess.run(cmd, cwd=".", capture_output=True)
            
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

    df_indiv = pd.DataFrame(study_results_indiv)
    df_apps = pd.DataFrame(study_results_app)
    
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

    print("Plots generated successfully in outputs directory.")
    
    # Copy to Memoria/figures/
    import shutil
    memoria_dir = Path("../Memoria/figures")
    memoria_dir.mkdir(parents=True, exist_ok=True)
    
    for img in ['resultados_latencia_individual.png', 'resultados_slo_individual.png', 
                'resultados_latencia_multisalto.png', 'resultados_slo_multisalto.png']:
        src = out_dir / img
        dst = memoria_dir / img
        if src.exists():
            shutil.copy(src, dst)
            print(f"Copied {img} to Memoria/figures/")

if __name__ == "__main__":
    run_benchmark()
