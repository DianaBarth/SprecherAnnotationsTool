import psutil
import Eingabe.config as config # Importiere das komplette config-Modul

class Systemressourcen:
    @staticmethod
    def get_ram_info():
        """Physischer RAM"""
        mem = psutil.virtual_memory()
        return {
            "total": mem.total,
            "available": mem.available,
            "used": mem.used,
            "free": mem.free,
            "percent": mem.percent
        }
    
    @staticmethod
    def get_swap_info():
        """Virtueller Speicher (Swap)"""
        swap = psutil.swap_memory()
        return {
            "total": swap.total,
            "used": swap.used,
            "free": swap.free,
            "percent": swap.percent,
            "sin": swap.sin,   # Bytes in Swap rein
            "sout": swap.sout  # Bytes aus Swap raus
        }

    @staticmethod
    def get_cpu_info():
        """CPU-Kerne und Auslastung"""
        return {
            "logical_cores": psutil.cpu_count(logical=True),
            "physical_cores": psutil.cpu_count(logical=False),
            "cpu_percent_total": psutil.cpu_percent(interval=1),
            "cpu_percent_per_core": psutil.cpu_percent(interval=1, percpu=True),
        }
    
    @staticmethod
    def get_disk_info():
        """Festplattennutzung (für Root/Standardpartition)"""
        usage = psutil.disk_usage('/')
        return {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": usage.percent
        }
    
    @staticmethod
    def get_network_stats():
        """Netzwerkstatistiken (Bytes gesendet/empfangen)"""
        net_io = psutil.net_io_counters()
        return {
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv,
            "packets_sent": net_io.packets_sent,
            "packets_recv": net_io.packets_recv,
            "errin": net_io.errin,
            "errout": net_io.errout,
            "dropin": net_io.dropin,
            "dropout": net_io.dropout
        }

    @staticmethod
    def print_all_resources():
        ram = Systemressourcen.get_ram_info()
        swap = Systemressourcen.get_swap_info()
        cpu = Systemressourcen.get_cpu_info()
        disk = Systemressourcen.get_disk_info()
        net = Systemressourcen.get_network_stats()

        print("=== Systemressourcen ===")
        print(f"RAM: {ram['used'] / (1024**3):.2f} GB benutzt von {ram['total'] / (1024**3):.2f} GB ({ram['percent']}%)")
        print(f"Swap: {swap['used'] / (1024**3):.2f} GB benutzt von {swap['total'] / (1024**3):.2f} GB ({swap['percent']}%)")
        print(f"CPU: {cpu['physical_cores']} physische Kerne, {cpu['logical_cores']} logische Kerne")
        print(f"CPU-Auslastung (gesamt): {cpu['cpu_percent_total']}%")
        print(f"CPU-Auslastung pro Kern: {', '.join(f'{p}%' for p in cpu['cpu_percent_per_core'])}")
        print(f"Festplatte: {disk['used'] / (1024**3):.2f} GB benutzt von {disk['total'] / (1024**3):.2f} GB ({disk['percent']}%)")
        print(f"Netzwerk: Gesendet {net['bytes_sent'] / (1024**2):.2f} MB, Empfangen {net['bytes_recv'] / (1024**2):.2f} MB")
