import pandas as pd
from pathlib import Path

class MicroservicesData:
    """Clase para almacenar y gestionar datos de microservicios desde CSV"""
    
    # Órdenes personalizadas para ciertos atributos
    CUSTOM_ORDERS = {
        'priority': ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'],
        'compute_intensity': ['HIGH', 'MEDIUM', 'LOW'],
        'statefulness': ['STATEFUL', 'STATELESS'],
        'redundancy_required': ['YES', 'NO']
    }
    
    def __init__(self, csv_path=None):
        """Inicializa la clase y carga los datos del CSV"""
        self.data = None
        self.apps = None
        
        if csv_path is None:
            csv_path = Path(__file__).resolve().parent.parent / "data" / "microservicios.csv"
        
        self.csv_path = Path(csv_path)
        self.load_data()
    
    def load_data(self):
        """Carga los datos del CSV y los almacena internamente"""
        try:
            self.data = pd.read_csv(self.csv_path)
            print(f"Datos cargados exitosamente desde: {self.csv_path}")
            print(f"Total de filas: {len(self.data)}")
            print(f"Columnas: {list(self.data.columns)}")
            
            self._organize_by_app()
            
        except FileNotFoundError:
            print(f"Error: El archivo {self.csv_path} no se encontró")
            raise
        except Exception as e:
            print(f"Error al cargar el CSV: {e}")
            raise
    
    def _organize_by_app(self):
        """Organiza los datos agrupados por aplicación"""
        self.apps = {}
        for app_id in self.data['app_id'].unique():
            app_data = self.data[self.data['app_id'] == app_id]
            app_name = app_data['app_name'].iloc[0]
            self.apps[app_id] = {
                'app_name': app_name,
                'services': app_data.to_dict('records')
            }
    
    def get_all_data(self):
        """Retorna el DataFrame completo"""
        return self.data
    
    def get_sorted_data(self, by, ascending=True):
        """Retorna los datos ordenados por un atributo específico"""
        if by not in self.data.columns:
            raise ValueError(f"Atributo '{by}' no existe. Atributos disponibles: {list(self.data.columns)}")
        
        sorted_data = self.data.copy()

        # Si el atributo tiene un orden personalizado, usarlo
        if by in self.CUSTOM_ORDERS:
            custom_order = self.CUSTOM_ORDERS[by]
            order_map = {value: index for index, value in enumerate(custom_order)}
            sort_rank = sorted_data[by].map(order_map)
            sorted_data = sorted_data.assign(
                _missing_sort_rank=sort_rank.isna().astype(int),
                _sort_rank=sort_rank.fillna(len(custom_order))
            )
            sorted_data = sorted_data.sort_values(
                by=["_missing_sort_rank", "_sort_rank"],
                ascending=[True, ascending]
            ).drop(columns=["_missing_sort_rank", "_sort_rank"])
        else:
            # Ordenamiento normal, dejando los NaN siempre al final
            sorted_data = sorted_data.sort_values(by=by, ascending=ascending, na_position="last")

        sorted_data = sorted_data.reset_index(drop=True)
        if sorted_data[by].isna().any():
            sorted_data[by] = sorted_data[by].fillna("Sin restricción")

        return sorted_data
    
    def print_summary(self):
        """Imprime un resumen de los datos cargados"""
        print("\n" + "="*60)
        print("RESUMEN DE MICROSERVICIOS")
        print("="*60)
        
        for app_id, app_info in self.apps.items():
            print(f"\n{app_id} - {app_info['app_name']}")
            print(f"Servicios: {len(app_info['services'])}")
            for service in app_info['services']:
                print(f"  {service['service_id']}: {service['service_name']} (Prioridad: {service['priority']})")


if __name__ == "__main__":
    ms_data = MicroservicesData()
    ms_data.print_summary()
    
    print("\n" + "="*60)
    print("EJEMPLOS DE ORDENAMIENTO")
    print("="*60)
    
    # Ejemplo 1: Ordenar por latencia máxima (ascendente)
    print("\nEjemplo 1: Servicios ordenados por latencia máxima (menor a mayor)")
    sorted_data = ms_data.get_sorted_data(by="latency_max_ms", ascending=True)
    print(sorted_data[['service_id', 'service_name', 'latency_max_ms']])
    
    # Ejemplo 2: Ordenar por prioridad (CRITICAL > HIGH > MEDIUM > LOW)
    print("\nEjemplo 2: Servicios ordenados por prioridad (crítico a bajo)")
    sorted_data = ms_data.get_sorted_data(by="priority", ascending=True)
    print(sorted_data[['service_id', 'service_name', 'priority']])
    
    # Ejemplo 3: Ordenar por intensidad computacional (HIGH > MEDIUM > LOW)
    print("\nEjemplo 3: Servicios ordenados por intensidad computacional (alta a baja)")
    sorted_data = ms_data.get_sorted_data(by="compute_intensity", ascending=True)
    print(sorted_data[['service_id', 'service_name', 'compute_intensity']])
    
    # Ejemplo 4: Ordenar por factor de escalabilidad (descendente)
    print("\nEjemplo 4: Servicios ordenados por escalabilidad (mayor a menor)")
    sorted_data = ms_data.get_sorted_data(by="scalability_factor", ascending=False)
    print(sorted_data[['service_id', 'service_name', 'scalability_factor']])
    
    # Ejemplo 5: Ordenar por throughput (ascendente)
    print("\nEjemplo 5: Servicios ordenados por throughput mínimo (menor a mayor)")
    sorted_data = ms_data.get_sorted_data(by="throughput_min_kbps", ascending=True)
    print(sorted_data[['service_id', 'service_name', 'throughput_min_kbps']])
