from collections import defaultdict
from itertools import product
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import os

def run_simulation(args):

    import matplotlib.pyplot as plt
    import random
    import seaborn as sns
    import copy
    import pandas as pd

    params, folder = args
    print(f"Starte Simulation mit Params: {params}, Folder: {folder}")
    

    max_age_range, MAX_GROUP_SIZE, ANNUAL_LEAVING_CHILDREN = params
    # --- Konstante Parameter, die sich nicht ändern ---
    START_YEAR = 0
    FUTURE_START_YEAR = 32
    TOTAL_YEARS = 51
    ANNUAL_NEW_GROUPS_MIN = 100
    NEW_YOUNG_CHILDREN = 1000
    AGE_DISTRIBUTION = {3: 0.2, 4: 0.2, 5: 0.2, 6: 0.2}
    LEAVING_PRIORITIZED_AGE_RANGE = (13, 16)

     # Datenstrukturen
    class Child:
        def __init__(self, age):
            self.age = age

    class Group:
        def __init__(self):
            self.children = []

        def add(self, child):
            self.children.append(child)

        def has_space(self):
            return len(self.children) < MAX_GROUP_SIZE

        def age_range_ok(self, age):
            if not self.children:
                return True
            ages = [c.age for c in self.children]
            return max(ages + [age]) - min(ages + [age]) <= max_age_range

        def total_children(self):
            return len(self.children)

    groups = []
    history = []

    for year in range(TOTAL_YEARS):
        all_children = [child for g in groups for child in g.children]

        # Altern
        for child in all_children:
            child.age += 1

    # Austritte
        leaving = []
       # 1. Alle Kinder eligible fürs Verlassen (auch ab 18)
        prio = [c for c in all_children if LEAVING_PRIORITIZED_AGE_RANGE[0] <= c.age <= LEAVING_PRIORITIZED_AGE_RANGE[1]]
        other = [c for c in all_children if c not in prio]

        # 2. Ziehe zuerst 75% aus der priorisierten Gruppe (falls möglich)
        num_prio = min(int(ANNUAL_LEAVING_CHILDREN * 0.75), len(prio))
        leaving = random.sample(prio, num_prio)

        # 3. Ziehe den Rest aus den anderen Kindern (egal welches Alter)
        num_rest = ANNUAL_LEAVING_CHILDREN - num_prio
        leaving.extend(random.sample(other, min(num_rest, len(other))))

        leaving = set(leaving)

        # 4. Entferne alle Kinder, die ausgewählt wurden ODER über 18 sind (sie verlassen immer)
        for g in groups:
            g.children = [c for c in g.children if c not in leaving and c.age < 18]

     # Aufgelöste Gruppen
        dissolved = [g for g in groups if not g.children]
        groups = [g for g in groups if g.children]

    # Umverteilung
        for g in dissolved:
            for child in g.children:
                placed = False
                for target in groups:
                    if target.has_space() and target.age_range_ok(child.age):
                        target.add(child)
                        placed = True
                        break
                if not placed:
                    new_g = Group()
                    new_g.add(child)
                    groups.append(new_g)

        # Neue Kinder
        new_children = []
        for age, ratio in AGE_DISTRIBUTION.items():
            new_children.extend([Child(age) for _ in range(int(NEW_YOUNG_CHILDREN * ratio))])

        # Bestehende Gruppen befüllen
        unplaced = []
        random.shuffle(new_children)
        for child in new_children:
            placed = False
            for g in sorted(groups, key=lambda x: x.total_children()):
                if g.has_space() and g.age_range_ok(child.age):
                    g.add(child)
                    placed = True
                    break
            if not placed:
                unplaced.append(child)

        # Neue Gruppen für unplatzierte
        new_groups = []
        unplaced_idx = 0
        while unplaced_idx < len(unplaced):
            g = Group()
            while g.has_space() and unplaced_idx < len(unplaced):
                if g.age_range_ok(unplaced[unplaced_idx].age):
                    g.add(unplaced[unplaced_idx])
                    unplaced_idx += 1
                else:
                    break
            groups.append(g)
            new_groups.append(g)

        # Minimum sichern
        while len(new_groups) < ANNUAL_NEW_GROUPS_MIN:
            g = Group()
            groups.append(g)
            new_groups.append(g)

        # Statistik
        total = sum(g.total_children() for g in groups)
        avg = total / len(groups) if groups else 0
        history.append((year, total, len(groups), avg))

    groups_at_30 = history[FUTURE_START_YEAR][2]  # Index 2 ist Anzahl Gruppen

    
    # --- Plot erzeugen ---
    years = [h[0] for h in history]
    total_children = [h[1] for h in history]
    total_groups = [h[2] for h in history]  
    avg_sizes = [h[3] for h in history]

    
    plt.figure(figsize=(10, 6))
    plt.plot(years, total_children, label="Gesamtanzahl Kinder")
    plt.plot(years, total_groups, label="Anzahl Gruppen", color="orange")
    plt.plot(years, avg_sizes, label="Ø Gruppengröße", color="green")
    plt.axvline(FUTURE_START_YEAR, color='red', linestyle='--', label="Stichtag")


    # Werte an der Linie annotieren
    val_kinder = total_children[FUTURE_START_YEAR]
    val_gruppen = total_groups[FUTURE_START_YEAR]
    val_durchschnitt = avg_sizes[FUTURE_START_YEAR]

    plt.text(FUTURE_START_YEAR + 0.5, val_kinder, f"{val_kinder}", color="blue")
    plt.text(FUTURE_START_YEAR + 0.5, val_gruppen, f"{val_gruppen}", color="orange")
    plt.text(FUTURE_START_YEAR + 0.5, val_durchschnitt, f"{val_durchschnitt:.2f}", color="green")

    plt.title(f"Max_Gruppengröße={MAX_GROUP_SIZE}, Verlassen={ANNUAL_LEAVING_CHILDREN}")
    plt.xlabel("Jahr")
    plt.ylabel("Anzahl")
    plt.legend()
    plt.tight_layout()

    filename1 = f"{folder}/sim_AR{max_age_range}MGS{MAX_GROUP_SIZE}_ALC{ANNUAL_LEAVING_CHILDREN}_G{groups_at_30}.png"
    plt.savefig(filename1)
    plt.close()
    
        # Tabelle mit Werten von Jahr 30 bis 60 anfügen
    years_table = years[FUTURE_START_YEAR:]
    total_children_table = total_children[FUTURE_START_YEAR:]
    total_groups_table = total_groups[FUTURE_START_YEAR:]
    avg_sizes_table = [f"{x:.2f}" for x in avg_sizes[FUTURE_START_YEAR:]]

    # Daten für Tabelle vorbereiten
    table_data = list(zip(years_table, total_children_table, total_groups_table, avg_sizes_table))

    # Tabellenspaltenüberschriften
    col_labels = ["Jahr", "Gesamtanzahl", "Anzahl Gruppen", "Ø Gruppengröße"]

    # Tabelle zeichnen
    the_table = plt.table(cellText=table_data,
                        colLabels=col_labels,
                        cellLoc='center',
                        loc='bottom',
                        bbox=[0.0, -0.6, 1, 0.5])  # position und Größe der Tabelle anpassen

    # Neuer Figure für die Tabelle
    plt.figure(figsize=(10, len(table_data)*0.3 + 1))  # Höhe dynamisch anpassen

    ax = plt.gca()
    ax.axis('off')  # Achsen ausblenden

    # Tabelle zeichnen
    the_table = ax.table(cellText=table_data,
                        colLabels=col_labels,
                        cellLoc='center',
                        loc='center')

    the_table.auto_set_font_size(False)
    the_table.set_fontsize(8)

    # Spaltenbreite schmaler, Zeilenhöhe größer
    for key, cell in the_table.get_celld().items():
        cell.set_width(0.1)
        cell.set_height(0.04)

    plt.title(f"Tabelle ab Jahr {FUTURE_START_YEAR}: Max_Gruppengröße={MAX_GROUP_SIZE}, Verlassen={ANNUAL_LEAVING_CHILDREN}")
    plt.tight_layout()

    filename2 = f"{folder}/table_AR{max_age_range}MGS{MAX_GROUP_SIZE}_ALC{ANNUAL_LEAVING_CHILDREN}_G{groups_at_30}.png"
    plt.savefig(filename2)
    plt.close()

def PlotAuswerten(folder):
    import os
    import re
    pattern = re.compile(r"sim_AR(\d+)MGS(\d+)_ALC(\d+)_G(\d+)\.png")
    data = []

    files = os.listdir(folder)
    print(f"Dateien im Ordner {folder}: {files}")

    for filename in files:
        match = pattern.match(filename)
        if match:
            print(f"Gefunden: {filename}")
            age_range = int(match.group(1))
            max_group_size = int(match.group(2))
            annual_leaving = int(match.group(3))
            groups_at_30 = int(match.group(4))
            data.append({
                "age_range": age_range,
                "max_group_size": max_group_size,
                "annual_leaving": annual_leaving,
                "groups_at_30": groups_at_30
            })
        else:
            print(f"Nicht passend: {filename}")

    if not data:
        print("Keine passenden Dateien gefunden.")
        return

    import pandas as pd
    import matplotlib.pyplot as plt
    import seaborn as sns

    df = pd.DataFrame(data)
    print(df.head())

    unique_age_ranges = df['age_range'].unique()

    for age_range in sorted(unique_age_ranges):
        df_subset = df[df['age_range'] == age_range]
        pivot = df_subset.pivot_table(
            index="annual_leaving",
            columns="max_group_size",
            values="groups_at_30",
            aggfunc='mean'
        )

        plt.figure(figsize=(14, 8))
        sns.heatmap(pivot, annot=True, fmt=".0f", cmap="YlGnBu")
        plt.title(f("Gruppenanzahl im Jahr {FUTURE_START_YEAR} (Altersrange: {age_range})")
        plt.xlabel("Maximale Gruppengröße")
        plt.ylabel("Austritte pro Jahr")
        plt.tight_layout()

        filename = os.path.join(folder, f"Auswertung_Heatmap_AR{age_range}.png")
        plt.savefig(filename)
        plt.close()
    print("Heatmaps gespeichert.")

combinations = list(product(range(4,5,1), range(30, 31, 1), range(760, 770, 1)))

def get_next_plot_folder(base_name="plots"):
    i = 1
    while True:
        folder_name = f"{base_name}{i}"
        if not os.path.exists(folder_name):
            return folder_name
        i += 1


if __name__ == "__main__":

    folder = get_next_plot_folder()
    os.makedirs(folder, exist_ok=True)
    max_workers = multiprocessing.cpu_count()
  
    print(f"Start: {folder}")

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
      executor.map(run_simulation, [(params, folder) for params in combinations], chunksize=25)

    
    print("fertig simuliert")

    PlotAuswerten(folder)
    print(f"fertig ausgewertet: {folder}")

