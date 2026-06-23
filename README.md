# TFG - Simulador NTN (Non-Terrestrial Networks)

Este repositorio contiene el código fuente del simulador híbrido desarrollado para el Trabajo Fin de Grado: **"Propuesta de algoritmo de distribución de microservicios en redes NTN"**.

## Descripción del Proyecto

El simulador permite evaluar y visualizar distintas estrategias de colocación de microservicios sobre una red híbrida compuesta por Vehículos Aéreos No Tripulados (UAVs / Drones) y Estaciones de Plataforma de Gran Altitud (HAPS).

Está diseñado en **Python** e incorpora una interfaz gráfica interactiva desarrollada con **Streamlit**. Su objetivo principal es calcular la latencia Round-Trip Time (RTT) y evaluar violaciones de Acuerdos de Nivel de Servicio (SLO) basándose en simulaciones de estrés estocástico y cálculos de enrutamiento dinámico sobre grafos de NetworkX.

Como caso de uso aplicado, el simulador parametriza y recrea la topología de una etapa del **Rally Dakar**.

## Estructura del Código

- `/data/`: Contiene los datasets en formato CSV con la información de los nodos (HAPS, UAVs), catálogos de microservicios (simples y por zonas) y la configuración paramétrica del Dakar.
- `/src/`: Núcleo algorítmico de la aplicación.
  - `load_ntn.py` y `load_microservices.py`: Carga y validación de entidades.
  - `random_placement.py`, `greedy_placement.py`, `clasification_placement.py`: Algoritmos de colocación implementados.
  - `simulate_requests.py`: Motor de estrés basado en el algoritmo de Dijkstra con penalizaciones dinámicas por congestión.
  - `visualizar_ntn.py`: Generación de mapas y gráficos espaciales.
  - `streamlit_app.py`: Frontend interactivo para ejecutar la simulación desde el navegador.
- `/outputs/`: Carpeta autogenerada donde el sistema exporta los reportes Markdown (.md), matrices CSV y las gráficas comparativas PNG con los resultados empíricos.
- `run_benchmark.py`: Script de automatización de experimentación. Ejecuta pruebas a gran escala y exporta los gráficos definitivos.

## Instalación y Ejecución

Para iniciar el simulador en tu entorno local, asegúrate de tener Python 3.9 o superior instalado.

1. Clona el repositorio e instala las dependencias:
```bash
pip install -r requirements.txt
```

2. Arranca la interfaz gráfica en Streamlit:
```bash
streamlit run src/streamlit_app.py
```
*(Alternativamente en Windows, puedes simplemente hacer doble clic en el archivo `Iniciar_Simulador.bat`)*

3. Para correr los experimentos formales de latencia y saturación:
```bash
python run_benchmark.py
```

## Algoritmos Implementados

1. **Algoritmo Aleatorio (Control):** Distribuye aleatoriamente las réplicas para establecer un umbral base de ineficiencia.
2. **Algoritmo Voraz (Greedy):** Minimiza la distancia euclídea saturando agresivamente la capa UAV del borde.
3. **Algoritmo de Clasificación (Propuesto):** Un orquestador inteligente que criba servicios por exigencia de computación vs latencia, delegando tareas pesadas al anillo estratosférico HAPS y las interacciones ultrarrápidas al enjambre de drones.

## Autor
**Manuel Alonso González**  
*Grado en Ingeniería Informática en Ingeniería del Software*
