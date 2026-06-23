# Parametros de microservicios y nodos NTN

Este documento resume los campos que usa el proyecto para definir los microservicios y los nodos NTN. El objetivo es que los datos sean interpretables, comparables y utiles para la colocacion aleatoria y para futuras politicas de asignacion.

## Microservicios

Los microservicios se describen en `data/microservicios.csv`. Cada fila representa un servicio concreto.

| Campo | Significado |
| --- | --- |
| `app_id` | Identificador de la aplicacion a la que pertenece el servicio. |
| `app_name` | Nombre legible de la aplicacion. |
| `service_id` | Identificador unico del microservicio dentro del proyecto. |
| `service_name` | Nombre legible del microservicio. |
| `priority` | Importancia operativa del servicio. Se usa para ordenar o priorizar servicios criticos frente a otros. |
| `latency_max_ms` | Latencia maxima tolerable, en milisegundos. |
| `throughput_min_kbps` | Ancho de banda minimo requerido, en kbps, segun la version original del catalogo. |
| `availability_target` | Objetivo de disponibilidad expresado en porcentaje o valor numerico equivalente. |
| `compute_intensity` | Intensidad de computo del servicio. En el catalogo se usa `HIGH`, `MEDIUM` o `LOW`. |
| `statefulness` | Indica si el servicio mantiene estado (`STATEFUL`) o no (`STATELESS`). |
| `redundancy_required` | Indica si el servicio debe replicarse (`YES`) o no (`NO`). |
| `scalability_factor` | Porcentaje de nodos de la red donde deberia existir una copia del servicio. Por ejemplo, `0.2` significa 20% de los nodos. |
| `cpu_demand` | Demanda de CPU del servicio, en GHz equivalentes al modelo de nodos NTN. |
| `mem_demand_gib` | Memoria requerida, en GiB. |
| `bandwidth_mbps` | Ancho de banda requerido por instancia, en Mbps. |
| `state_size_mb` | Tamano del estado del servicio, en MB. Para servicios sin estado suele ser `0`. |

### Como se usa en la colocacion

- `cpu_demand`, `mem_demand_gib`, `bandwidth_mbps` y `state_size_mb` determinan si una replica cabe en un nodo.
- `scalability_factor` define cuantas replicas se intentan colocar en total.
- `state_size_mb` sirve tambien como aproximacion del coste de migracion o de persistencia.
- `priority`, `latency_max_ms` y `compute_intensity` ayudan a decidir futuros criterios de ordenamiento o filtrado.

## Aplicaciones (Cadenas de Microservicios)

Las aplicaciones se describen en `data/aplicaciones.csv`. Cada fila representa una aplicacion formada por una secuencia de microservicios que deben ejecutarse en orden (Service Chaining).

| Campo | Significado |
| --- | --- |
| `app_id` | Identificador unico de la aplicacion. |
| `app_name` | Nombre legible de la aplicacion. |
| `chain` | Secuencia de identificadores de microservicios separados por punto y coma (ej: `EME-S01;EME-S02;EME-S03`). |
| `latency_max_ms` | Latencia maxima tolerable global para la ejecucion completa de la cadena, en milisegundos. |
| `zone_id` | Zona geografica desde donde se originan las peticiones a la aplicacion. |

### Como se usa en la simulacion

En el simulador (`src/simulate_requests.py`), cuando se evalua una aplicacion:
- La peticion se origina en la zona indicada por `zone_id`.
- Se calcula la latencia sumando el recorrido desde el usuario hasta el nodo que aloja el primer microservicio de la cadena, saltando secuencialmente a los nodos de los siguientes microservicios de la cadena, y finalmente regresando al usuario.
- A cada salto de red y al tiempo de procesamiento en el nodo se le aplica una varianza aleatoria del +/- 10% para simular condiciones reales.
- El resultado queda reflejado en `outputs/app_requests_simulation.csv`.

## Nodos NTN

Los nodos se describen en `data/nodos_ntn.csv`. Cada fila representa un nodo de la red.

| Campo | Significado |
| --- | --- |
| `node_id` | Identificador unico del nodo. |
| `node_type` | Tipo del nodo. En el proyecto actual se usan `HAPS` y `UAV`. |
| `x` | Coordenada horizontal del nodo en el mapa del escenario. |
| `y` | Coordenada vertical del nodo en el mapa del escenario. |
| `cpu_capacity_ghz` | Capacidad total de CPU disponible en el nodo, en GHz. |
| `mem_capacity_gib` | Memoria total disponible, en GiB. |
| `bandwidth_capacity_mbps` | Ancho de banda disponible para servicios, en Mbps. |
| `storage_capacity_gb` | Almacenamiento util disponible, en GB. |

### Interpretacion de los tipos de nodo

- `HAPS`: nodos mas capaces y estables, pensados para agregacion, soporte de servicios mas pesados y mayor cobertura.
- `UAV`: nodos mas ligeros y numerosos, con capacidad menor pero utiles para servicios de borde y distribucion.

### Como se usa en la colocacion

El algoritmo de colocacion compara las demandas del microservicio con las capacidades disponibles del nodo:

- CPU: `cpu_demand` frente a `cpu_capacity_ghz`
- Memoria: `mem_demand_gib` frente a `mem_capacity_gib`
- Red: `bandwidth_mbps` frente a `bandwidth_capacity_mbps`
- Almacenamiento: `state_size_mb` transformado a GB frente a `storage_capacity_gb`

Si el nodo tiene capacidad suficiente, la replica se coloca y se descuentan sus recursos.

## Archivos relacionados

- `src/visualizar_ntn.py`: visualizacion de la red NTN.

Note: The visualization and surface/stage CSVs can be expressed either in geographic degrees
(lon/lat) or in planar kilometers. Use the `--units km` flag when running
`src/visualizar_ntn.py` if the `data/stage_oficial.csv` and `data/superficie_prueba.csv`
use 1 unit = 1 km coordinates (for example the straight 50 km test segment).
- `src/random_placement.py`: algoritmo aleatorio de colocacion de microservicios.
- `src/greedy_placement.py`: algoritmo voraz de colocacion priorizando cercania a las zonas de origen.
- `src/clasification_placement.py`: algoritmo voraz que clasifica microservicios por su latencia y requerimientos de CPU (prioriza UAVs para baja latencia y HAPS para alta CPU).
- `src/load_ntn.py`: carga de nodos NTN y conexiones.
- `src/load_microservices.py`: carga y ordenacion de microservicios.
- `src/simulate_requests.py`: simulador de llamadas individuales a microservicios y de llamadas multisalto a cadenas de aplicaciones.
- `src/streamlit_app.py`: interfaz grafica web de usuario para el control de todo el proyecto.

## Nota de modelo

Los valores del catalogo de microservicios y de capacidades de nodos estan pensados para ser coherentes entre si dentro del proyecto. No representan medidas fisicas reales de un sistema concreto, sino una base consistente para evaluar colocacion, saturacion y reparto de carga.