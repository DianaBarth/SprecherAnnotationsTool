import os
import re
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Ordner mit den Plot-Dateien
folder = "plots"

# Regex zum Extrahieren der Werte aus Dateinamen
pattern = re.compile(r"sim_AR(\d+)MGS(\d+)_ALC(\d+)_G(\d+)\.png")

data = []

# Dateien durchgehen
for filename in os.listdir(folder):
    match = pattern.match(filename)
    if match:
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

# DataFrame erstellen
df = pd.DataFrame(data)

# ----------------------------
# Beispiel 1: Heatmap (Pivot-Tabelle notwendig)
# ----------------------------

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
    plt.title(f"Gruppenanzahl im Jahr 30 (Altersrange: {age_range})")
    plt.xlabel("Maximale Gruppengröße")
    plt.ylabel("Austritte pro Jahr")
    plt.tight_layout()

    filename = f"plots/Auswertung_Heatmap_AR{age_range}.png"
    plt.savefig(filename)
    plt.close()
