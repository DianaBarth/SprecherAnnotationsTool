from collections import defaultdict
from itertools import product
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import os
import pandas as pd
from glob import glob
import random
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import random
import string
import math
from itertools import cycle
from log_manager import LogManager
from sklearn.cluster import KMeans
import numpy as np
import matplotlib.cm as cm
from math import dist

STARTJAHR = 1968
ANZAHL_JAHRE = 52

def hole_wert_fuer_jahr(zuordnung, jahr, standardwert=0):
    for zeitraum, wert in zuordnung.items():
        if jahr in zeitraum:
            return wert
    return standardwert

def entfernung_zum_zentrum(coord, MITTE_POS):
    x, y = coord
    return abs(x - MITTE_POS) + abs(y - MITTE_POS)  # Manhattan-Distanz


def generiere_zufaelligen_buchstaben():
    return random.choice(string.ascii_uppercase)


def berechne_haueser(FLAECHE_SEITE,speicherordner, printPlots=True, printJahr = 2000):
  
    aktive_haeuser_pro_jahr = {}
    beobachtetes_haus = None  # globaler Platzhalter
    beobachteter_Abstand = 7.5

    MITTE_SIZE = 4.5
    MITTE_START = (FLAECHE_SEITE - MITTE_SIZE) / 2
    MITTE_POS = FLAECHE_SEITE / 2

    # Raster & Jahre (jeweils inkl. Endjahr)

    raster_jahresbereiche = [
        (1965, 1970, 6.0),
        (1971, 1984, 3.0),
        (1985, 2000, 1.5),
        (2001, 2020, 0.75), 
    ]

    def berechne_hauspositionen(abstand_km):
        """Berechnet Häuserkoordinaten zentriert um die Mitte der Fläche."""
        # Beobachtetes Haus einmalig setzen, falls noch nicht gesetzt
        nonlocal beobachtetes_haus
        
        beobachtbare_haeuser = []


        gesamt_haeuser_achse = int(FLAECHE_SEITE / abstand_km)
        koordinaten = []

        # Um das Raster zentriert um Mitte zu bekommen, verschieben wir das Grid
        start_verschiebung = MITTE_POS - (gesamt_haeuser_achse - 1)/2 * abstand_km

        mitte_start = (FLAECHE_SEITE - MITTE_SIZE) / 2
        mitte_ende = mitte_start + MITTE_SIZE

        for i in range(gesamt_haeuser_achse):
            x_pos = start_verschiebung + i * abstand_km
            for j in range(gesamt_haeuser_achse):
                y_pos = start_verschiebung + j * abstand_km
                # Zentrum frei lassen
               # Neue, präzisere Abstandskontrolle:
                dx = max(0, MITTE_START - x_pos, x_pos - (MITTE_START + MITTE_SIZE))
                dy = max(0, MITTE_START - y_pos, y_pos - (MITTE_START + MITTE_SIZE))
                abstand_zum_mitteblock = (dx**2 + dy**2) ** 0.5

                if abstand_zum_mitteblock < abstand_km:
                    continue

                koordinaten.append((round(x_pos,4), round(y_pos,4)))

                # Prüfe auf Beobachtungsabstand (7.5 km vom Zentrumsrand)
                if abs(abstand_zum_mitteblock -beobachteter_Abstand) < abstand_km / 2:
                    beobachtbare_haeuser.append((round(x_pos,4), round(y_pos,4)))

         
            if beobachtetes_haus is None and beobachtbare_haeuser:
                beobachtetes_haus = beobachtbare_haeuser[0]

        return koordinaten


    def gruppiere_haus_ringe(coords):
        ringe = defaultdict(list)
        for c in coords:
            dist = round(entfernung_zum_zentrum(c, MITTE_POS), 4)
            ringe[dist].append(c)
        return [runde_ringe for _, runde_ringe in sorted(ringe.items())]

    def plot_haeuser(jahr, neue_haeuser, bestehende_haeuser,beobachtetes_haus=None):
        plt.figure(figsize=(8,8))

        if bestehende_haeuser:
            x_alt, y_alt = zip(*bestehende_haeuser)
            plt.scatter(x_alt, y_alt, c='blue', s=10, label='Bestehende Häuser')
        if neue_haeuser:
            x_neu, y_neu = zip(*neue_haeuser)
            plt.scatter(x_neu, y_neu, c='green', s=10, label='Neue Häuser')
        
        # Nur zeichnen, wenn das beobachtete Haus aktuell gebaut ist:
        if beobachtetes_haus is not None and (beobachtetes_haus in bestehende_haeuser or beobachtetes_haus in neue_haeuser):
            x_b, y_b = beobachtetes_haus
            plt.scatter([x_b], [y_b], c='magenta', s=40, marker='*', label='Beobachtetes Haus')

        ax = plt.gca()
        quadrat = patches.Rectangle(
            (MITTE_START, MITTE_START),
            MITTE_SIZE, MITTE_SIZE,
            linewidth=0, facecolor='red', alpha=0.3, label='Zentrum (frei)'
        )
        ax.add_patch(quadrat)

        plt.title(f"Häuserverteilung Jahr {jahr}\nNeu: {len(neue_haeuser)} | Bestehend: {len(bestehende_haeuser)}",
          fontsize=12, pad=50)
        
        if jahr == printJahr:
            print(f"{speicherordner} : {len(neue_haeuser) + len(bestehende_haeuser)}")

        plt.legend(loc='upper center', bbox_to_anchor=(0.5, 1.1), ncol=3, borderaxespad=0., handletextpad=0.5, columnspacing=1)

        plt.subplots_adjust(top=0.75)  # mehr Abstand oben, damit Legende nicht überlappt

        plt.xlim(0, FLAECHE_SEITE)
        plt.ylim(0, FLAECHE_SEITE)
        plt.gca().set_aspect('equal')
   
        plt.grid(True)

        if speicherordner:
            os.makedirs(speicherordner, exist_ok=True)
            dateipfad = os.path.join(speicherordner, f"haeuser_{jahr}.png")
            plt.savefig(dateipfad)
            plt.close()
        else:
            plt.show()

    MAX_HAEUSER_PRO_JAHR = {}
    aktive_haeuser_gesamt = set()
    jahr_letzter_bau = None
    
# Erstes Raster komplett bauen im ersten Rasterjahr (z.B. 1970)

    for startjahr, endjahr, raster_abstand in raster_jahresbereiche:

        coords = sorted(berechne_hauspositionen(raster_abstand))
        ringe = gruppiere_haus_ringe(coords)
        ring_index = 0

        jahre_im_intervall = list(range(startjahr, endjahr + 1))
        anzahl_jahre = len(jahre_im_intervall)


        for i, jahr in enumerate(jahre_im_intervall):           
            neue_heute = set()

            # Anzahl Ringe, die nach diesem Jahr gebaut sein sollten
            total_ringe = len(ringe)
            ringe_pro_jahr = total_ringe / anzahl_jahre
            bis_jetzt_ringe = int(round(ringe_pro_jahr * (i + 1)))

            # Füge alle noch nicht gebauten Ringe hinzu, die bis zum aktuellen Jahr dran sind
            while ring_index < bis_jetzt_ringe and ring_index < total_ringe:
                neue_heute.update(ringe[ring_index])
                ring_index += 1

            # Nur neue Häuser, die noch nicht gebaut wurden
            neue_heute = neue_heute - aktive_haeuser_gesamt
            aktive_haeuser_gesamt |= neue_heute
            aktive_haeuser_pro_jahr[jahr] = list(aktive_haeuser_gesamt)

            if printPlots:
                bestehend = aktive_haeuser_gesamt - neue_heute
                plot_haeuser(jahr, neue_heute, bestehend,beobachtetes_haus)

            MAX_HAEUSER_PRO_JAHR = {}

        aktive_haeuser_gesamt = set()
        aktive_haeuser_pro_jahr = {}

        for startjahr, endjahr, raster_abstand in raster_jahresbereiche:

            coords = sorted(berechne_hauspositionen(raster_abstand))
            ringe = gruppiere_haus_ringe(coords)
            ring_index = 0

            jahre_im_intervall = list(range(startjahr, endjahr + 1))
            anzahl_jahre = len(jahre_im_intervall)

            for i, jahr in enumerate(jahre_im_intervall):           
                neue_heute = set()

                total_ringe = len(ringe)
                ringe_pro_jahr = total_ringe / anzahl_jahre
                bis_jetzt_ringe = int(round(ringe_pro_jahr * (i + 1)))

                while ring_index < bis_jetzt_ringe and ring_index < total_ringe:
                    neue_heute.update(ringe[ring_index])
                    ring_index += 1

                neue_heute = neue_heute - aktive_haeuser_gesamt
                aktive_haeuser_gesamt |= neue_heute

                if printPlots:
                    bestehend = aktive_haeuser_gesamt - neue_heute
                    plot_haeuser(jahr, neue_heute, bestehend, beobachtetes_haus)

                MAX_HAEUSER_PRO_JAHR[jahr] = len(aktive_haeuser_gesamt)
                aktive_haeuser_pro_jahr[jahr] = list(aktive_haeuser_gesamt)

    return MAX_HAEUSER_PRO_JAHR, aktive_haeuser_pro_jahr, beobachtetes_haus

def dist(a, b):
    return math.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)

def simuliere_busfahrten(
    koordinaten,
    anzahl_busse,
    wartezeit_pro_haus_sek,
    hinfahrt_kmh,
    rueckfahrt_kmh_schnell,
    rueckfahrt_schwelle_min,
    flaeche_seite,
    beobachtetes_haus=None, 
    plotte_Route = True,
    speicherordner ="bus"
):
    zentrum = (flaeche_seite / 2, flaeche_seite / 2)

    bus_routen = []
    
    # In numpy umwandeln für KMeans
    koordinaten_np = np.array(koordinaten)
    kmeans = KMeans(n_clusters=anzahl_busse, n_init=10)
    labels = kmeans.fit_predict(koordinaten_np)

    zeiten_pro_bus = []
    zeiten_beobachtet = []

    for bus_index in range(anzahl_busse):
        route = koordinaten_np[labels == bus_index].tolist()

        # Sortiere nach Luftlinie vom Zentrum
        route.sort(key=lambda x: dist(x, zentrum))

        bus_routen.append(route)
        total_dist_hin = 0
        total_dist_zurueck = 0
        zeit_bis_beobachtet = None
        zeit_ab_beobachtet = None
        zeit_gesamt_min = 0

        aktuelle_position = zentrum
        beobachtetes_haus_erreicht = False
        zeitsumme_bis_beobachtet = 0

        for haus in route:
            strecke_hin = dist(aktuelle_position, haus)
            zeit_hin_min = (strecke_hin / hinfahrt_kmh) * 60
            total_dist_hin += strecke_hin
            warte_min = wartezeit_pro_haus_sek / 60
            zeit_gesamt_min += zeit_hin_min + warte_min

            zeitsumme_bis_beobachtet += zeit_hin_min + warte_min

            if beobachtetes_haus and not beobachtetes_haus_erreicht and np.allclose(haus, beobachtetes_haus):
                zeit_bis_beobachtet = zeitsumme_bis_beobachtet
                beobachtetes_haus_erreicht = True

            aktuelle_position = haus

        # Rückfahrt
        rueckfahrt_dist = dist(aktuelle_position, zentrum)
        rueckfahrt_zeit_langsam = (rueckfahrt_dist / hinfahrt_kmh) * 60
        rueckfahrt_zeit_schnell = (rueckfahrt_dist / rueckfahrt_kmh_schnell) * 60

        rueckfahrt_zeit_min = rueckfahrt_zeit_schnell if rueckfahrt_zeit_langsam > rueckfahrt_schwelle_min else rueckfahrt_zeit_langsam
        zeit_gesamt_min += rueckfahrt_zeit_min

        if beobachtetes_haus_erreicht:
            zeit_ab_beobachtet = zeit_gesamt_min - zeit_bis_beobachtet
            zeiten_beobachtet.append((bus_index, round(zeit_bis_beobachtet, 2), round(zeit_ab_beobachtet, 2)))

        zeiten_pro_bus.append(round(zeit_gesamt_min, 2))

    max_zeit = round(max(zeiten_pro_bus), 2)

    plt.figure(figsize=(8, 8))
    ax = plt.gca()

    if plotte_Route:

        # Farbskala je Bus
        farben = cm.get_cmap('tab10', len(bus_routen))

        # Routen
        for i, route in enumerate(bus_routen):
            farbe = farben(i)
            x = [zentrum[0]] + [p[0] for p in route] + [zentrum[0]]
            y = [zentrum[1]] + [p[1] for p in route] + [zentrum[1]]

            plt.plot(x, y, marker='o', color=farbe, label=f'Bus {i}', linewidth=2, markersize=4)

        # Zentrum
        MITTE_SIZE = 4.5
        MITTE_START = (flaeche_seite - MITTE_SIZE) / 2
        quadrat = patches.Rectangle(
            (MITTE_START, MITTE_START),
            MITTE_SIZE, MITTE_SIZE,
            linewidth=0, facecolor='red', alpha=0.3, label='Zentrum (frei)'
        )
        ax.add_patch(quadrat)
        plt.scatter(*zentrum, c='red', s=100, zorder=5)

        # Beobachtetes Haus (falls vorhanden)
        if beobachtetes_haus is not None:
            plt.scatter(*beobachtetes_haus, c='magenta', s=80, marker='*', label='Beobachtetes Haus', zorder=6)

    
    titel =  f"Max-Zeit (Minuten): {max_zeit} \n"

    if zeiten_beobachtet:
        for bus_index, hin_min, rueck_min in zeiten_beobachtet:
            titel+= f"Beobachtetes Haus: \n  vorher {hin_min} min, nachher {rueck_min} min"

        plt.title(titel)
        plt.xlabel("X [km]")
        plt.ylabel("Y [km]")
        plt.xlim(0, flaeche_seite)
        plt.ylim(0, flaeche_seite)
        plt.gca().set_aspect('equal')
        plt.grid(True)
 #       plt.legend(loc='upper center', bbox_to_anchor=(0.5, 1.1), ncol=3)
        plt.tight_layout()
        if speicherordner:
            os.makedirs(speicherordner, exist_ok=True)
            dateipfad = os.path.join(speicherordner, f"Busrouten vorher {hin_min} min, nachher {rueck_min} min.png")
            plt.savefig(dateipfad)
            plt.close()
        else:
            plt.show()





    return max_zeit, zeiten_pro_bus, zeiten_beobachtet


def (jahres_dict):
    if not jahres_dict:
        return {}

    jahre_sortiert = sorted(jahres_dict.keys())
    result = {}
    start = jahre_sortiert[0]
    last_wert = jahres_dict[start]

    for i in range(1, len(jahre_sortiert)):
        jahr = jahre_sortiert[i]
        aktueller_wert = jahres_dict[jahr]

        if aktueller_wert != last_wert:
            result[range(start, jahr)] = last_wert
            start = jahr
            last_wert = aktueller_wert

    result[range(start, jahre_sortiert[-1] + 1)] = last_wert
    return result

def gruppiere_jahre(jahr_dict, gruppenschritt=5):
    gruppiert = {}
    jahre = sorted(jahr_dict.keys())
    start = jahre[0]
    aktueller_range = range(start, start + gruppenschritt)
    werte_liste = []

    for jahr in jahre:
        wert = jahr_dict[jahr]
        if jahr not in aktueller_range:
            gruppiert[aktueller_range] = max(werte_liste)
            aktueller_range = range(jahr, jahr + gruppenschritt)
            werte_liste = []
        werte_liste.append(wert)

    if werte_liste:
        gruppiert[aktueller_range] = max(werte_liste)

    return gruppiert

def ermittle_minimale_gruppen_und_kinder(offset_KINDERFAKTOR, MAX_HAEUSER_PRO_JAHR, maximale_gruppengroesse, alter_verteilung, auslastung=0.8, min_kinder=4):
    """
    Berechnet MIN_NEUE_GRUPPEN_PRO_JAHR und NEUE_KINDER so, dass MAX_HAEUSER_PRO_JAHR bestmöglich genutzt wird.
    :param offset_KINDER: Zahl, die dazuaddiert wird
    :param MAX_HAEUSER_PRO_JAHR: dict mit {jahr: anzahl max häuser}
    :param maximale_gruppengroesse: maximale Gruppengröße (z. B. 20)
    :param alter_verteilung: dict {alter: anteil} für neue Kinder
    :param auslastung: gewünschte durchschnittliche Auslastung pro Gruppe (z. B. 0.8)
    :param min_kinder: Mindestanzahl Kinder in Gruppe, damit Haus belegt
    :return: (MIN_NEUE_GRUPPEN_PRO_JAHR, NEUE_KINDER)
    """
    MIN_NEUE_GRUPPEN_PRO_JAHR = {}
    NEUE_KINDER = {}

    durchschnittliche_gruppengroesse = max(int(maximale_gruppengroesse * auslastung), min_kinder)

    for jahr in range(STARTJAHR, STARTJAHR +ANZAHL_JAHRE ):
        max_haeuser = hole_wert_fuer_jahr(MAX_HAEUSER_PRO_JAHR, jahr)
        min_gruppen = max_haeuser  # ideal: ein Haus pro Gruppe
        gesamt_kinder = min_gruppen * durchschnittliche_gruppengroesse

        # NEUE_KINDER-Verteilung erfordert mind. 1 Kind pro Alter
        mindestens_ein_kind_pro_alter = sum(1 for a in alter_verteilung if alter_verteilung[a] > 0)

        # Runden auf 10er/50er, wenn gewünscht
        MIN_NEUE_GRUPPEN_PRO_JAHR[jahr] = min_gruppen
        NEUE_KINDER[jahr] = max(round(gesamt_kinder * offset_KINDERFAKTOR,0), mindestens_ein_kind_pro_alter)

    return gruppiere_jahre(MIN_NEUE_GRUPPEN_PRO_JAHR), gruppiere_jahre(NEUE_KINDER)

def simuliere_gruppen(argumente):
    try:

        maximale_altersspanne, maximale_gruppengroesse, durchlauf_nummer, ordnerpfad, MAX_HAEUSER_PRO_JAHR, MIN_NEUE_GRUPPEN_PRO_JAHR, NEUE_KINDER,ALTER_VERTEILUNG = argumente

        print(f"Starte Simulation mit: Altersspanne={maximale_altersspanne}, Gruppengröße={maximale_gruppengroesse}, Lauf={durchlauf_nummer}")

        verlauf = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        verlauf_kinder = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
  

        beobachteteGruppe = {
            2000: [
                    {"namensbuchstabe:" : "J" , "alter": 5, "Neu": True},
                    {"namensbuchstabe:" : "U" , "alter": 3, "Neu": True},
                    {"namensbuchstabe:" : "M" , "alter": 4, "Neu": True},
                    {"namensbuchstabe:" : "R" , "alter": 4, "Neu": True},
                    {"namensbuchstabe:" : "P" , "alter": 3, "Neu": True},
                ],

            2002: [
                    {"namensbuchstabe:" : "D" , "alter": 3, "Neu": True},
                    {"namensbuchstabe:" : "DU" , "alter": 4, "Neu": True}
                 ],
            2003: [
                    {"namensbuchstabe:" : "E" , "alter": 8, "Neu": True},
                    {"namensbuchstabe:" : "M" , "alter": 7, "Neu": True},
                    {"namensbuchstabe:" : "S" , "alter": 4, "Neu": False},
                    {"namensbuchstabe:" : "T" , "alter": 6, "Neu": False},
                    {"namensbuchstabe:" : "F" , "alter": 7, "Neu": False},
                    {"namensbuchstabe:" : "S" , "alter": 7, "Neu": False},
                    {"namensbuchstabe:" : "H" , "alter": 7, "Neu": False},
                    {"namensbuchstabe:" : "J" , "alter": 8, "Neu": False},
                    {"namensbuchstabe:" : "J" , "alter": 8, "Neu": False},
                    {"namensbuchstabe:" : "K" , "alter": 8, "Neu": False},
                    {"namensbuchstabe:" : "K" , "alter": 8, "Neu": False},
                    {"namensbuchstabe:" : "C" , "alter": 8, "Neu": False}, 
                ],
            2004:
                [
                    {"namensbuchstabe:" : "F" , "alter": 8, "Neu": True},
                    {"namensbuchstabe:" : "N" , "alter": 9, "Neu": True},                   
                ],
             2005:
                [
                    {"namensbuchstabe:" : "T" , "alter": 8, "Neu": True},
                    {"namensbuchstabe:" : "H" , "alter": 9, "Neu": True},                   
                ],
              2006:
                [
                    {"namensbuchstabe:" : "F" , "alter": 9, "Neu": True},
                    {"namensbuchstabe:" : "C" , "alter": 10, "Neu": True},                   
                ],
               2007:
                [
                    {"namensbuchstabe:" : "R" , "alter": 10, "Neu": True},
                    {"namensbuchstabe:" : "S" , "alter": 11, "Neu": True},                   
               ]  , 

        }

        MIN_NEUE_GRUPPEN_PRO_JAHR = {
            range(1970, 1975): 15,
            range(1975, 1980): 50,
            range(1980, 1990): 100,
            range(1990, 2001): 100,
            range(2001, 2020): 200,
        }

        NEUE_KINDER = {
            range(1970, 1975): 50,
            range(1975, 1980): 100,
            range(1980, 1985): 150,
            range(1985,1990): 200,
            range(1990, 1995): 250,
            range(1995,2000): 500,
            range(2000, 2005): 1000,
            range(2005,2010): 1250,
            range(2010,2020):1500,
        }

        MAX_GRUPPENGROESSE_PRO_ALTER = {
            range(5, 6): 4,
            range(6, 7): 5,
            range(7, 8): 6,
            range(8, 9): 19,
            range(9, 10): 21,
            range(10, 11): 23,
            range(11, 12): 25,
            range(13, 14): 27,
            range(15, 16): 29,
            range(16, 18): 31,
        }

        PRIORITAETSALTER = (13, 16)
        PRIORITAETSALTER_RESTQUOTE =0.1
        MIN_KINDER = 4

        def ermittle_maximale_gruppengroesse(alter):
            return hole_wert_fuer_jahr(MAX_GRUPPENGROESSE_PRO_ALTER, alter, standardwert=maximale_gruppengroesse)

        class Kind:
            def __init__(self, Alter,Eintrittsjahr = None,Namensbuchstabe = None):
                self.alter = Alter                       
                self.eintrittsjahr = Eintrittsjahr
                self.namensbuchstabe = Namensbuchstabe
                self.namensNummer = 1

            def set_Namensnummer (self,NamensNummer):
                self.namensNummer = NamensNummer   
        
            def get_Name(self):
                return self.namensbuchstabe + str(self.namensNummer)

        class Gruppe:
            def __init__(self):
                self.kinder = []
                self.offen = True  # neue Gruppen sind anfangs offen

            def hinzufuegen(self, kind):
                self.kinder.append(kind)

            def hat_platz(self):
                if not self.kinder:
                    return True
                aeltestes = max(k.alter for k in self.kinder)
                maximale_groesse = ermittle_maximale_gruppengroesse(aeltestes)
                return len(self.kinder) < maximale_groesse

            def altersspanne_ok(self, alter):
                if not self.kinder:
                    return True
                alle_alter = [k.alter for k in self.kinder] + [alter]
                return max(alle_alter) - min(alle_alter) <= maximale_altersspanne

            def anzahl_kinder(self):
                return len(self.kinder)
            
            def durchschnittsalter(self):
                if not self.kinder:
                    return 0
                return sum(k.alter for k in self.kinder) / len(self.kinder)
            
            def vergebe_namensnummern(self):
                    buchstabe_to_kinder = defaultdict(list)

                    # Sammle Kinder pro Buchstabe
                    for kind in self.kinder:
                        buchstabe_to_kinder[kind.namensbuchstabe].append(kind)

                    # Sortiere nach Eintrittsjahr und vergebe laufende Nummern
                    for buchstabe, kinder_liste in buchstabe_to_kinder.items():
                        kinder_liste.sort(key=lambda k: k.eintrittsjahr)
                        for nummer, kind in enumerate(kinder_liste, 1):
                            kind.set_Namensnummer(nummer)

        def berechne_anzahl_abgaenge(gruppen, jahr, hausgrenze, durchschnitt):
            max_haeuser = hole_wert_fuer_jahr(hausgrenze, jahr, 999)
            belegte_haeuser = sum(1 for g in gruppen if g.anzahl_kinder() > 0)
            ueberschuss = belegte_haeuser - max_haeuser
            if ueberschuss <= 0:
                return 0, max_haeuser, belegte_haeuser
            geschaetzte_abgaenge = int(ueberschuss * durchschnitt)
            return geschaetzte_abgaenge, max_haeuser, belegte_haeuser

        def entferne_abgaenge_mit_prioritaet(gruppen, abgaenge, prioritaetsalter, restquote=0.25, min_kinder=MIN_KINDER):
            Anzahl_Kinder = []
            for gid, gruppe in enumerate(gruppen):
                if not gruppe.offen:
                    continue
                for kind in gruppe.kinder:
                    Anzahl_Kinder.append((gid, kind))

            prior_kinder = [k for k in Anzahl_Kinder if k[1].alter in prioritaetsalter]
            andere_kinder = [k for k in Anzahl_Kinder if k[1].alter not in prioritaetsalter]

            # Nur Kinder aus Gruppen entfernen, die groß genug bleiben würden
            def filter_abgaenge(kinderliste):
                gueltige = []
                for gid, kind in kinderliste:
                    gruppe = gruppen[gid]
                    if gruppe.anzahl_kinder() > min_kinder:
                        gueltige.append((gid, kind))
                return gueltige

            prior_kinder = filter_abgaenge(prior_kinder)
            andere_kinder = filter_abgaenge(andere_kinder)

            min_prior_kinder = int(len(prior_kinder) * restquote)
            max_entfernbar_prior = max(len(prior_kinder) - min_prior_kinder, 0)

            verbleib_abgaenge = abgaenge
            entfern_prior = min(verbleib_abgaenge, len(prior_kinder) - min_prior_kinder)
            prior_entfernen = random.sample(prior_kinder, entfern_prior) if entfern_prior > 0 else []
            verbleib_abgaenge -= entfern_prior

            andere_entfernen = []
            if verbleib_abgaenge > 0:
                entfern_andere = min(verbleib_abgaenge, len(andere_kinder))
                andere_entfernen = random.sample(andere_kinder, entfern_andere)

            zu_entfernende = prior_entfernen + andere_entfernen
            for gid, kind in zu_entfernende:
                gruppen[gid].kinder.remove(kind)

            gruppen = [g for g in gruppen if g.anzahl_kinder() > 0]
            return gruppen
          

        def verteile_und_entferne_kleine_gruppen(gruppen, min_kinder, max_haeuser):
            kleine_gruppen = [g for g in gruppen if g.anzahl_kinder() < min_kinder and g.offen]
            andere_gruppen = [g for g in gruppen if g.anzahl_kinder() >= min_kinder and g.offen]

            andere_gruppen.sort(key=lambda g: g.anzahl_kinder(), reverse=True)

            verteilte_kinder = []
            nicht_verteilbare_gruppen = []

            for kleine_gruppe in kleine_gruppen:
                kinder_zur_verteilung = kleine_gruppe.kinder.copy()
                kleine_gruppe.kinder.clear()
                erfolgreich_verteilt = True

                for kind in kinder_zur_verteilung:
                    verteilt = False
                    for gruppe in andere_gruppen:
                        if gruppe.offen and gruppe.hat_platz() and gruppe.altersspanne_ok(kind.alter):
                            gruppe.hinzufuegen(kind)
                            verteilt = True
                            break
                    if not verteilt:
                        erfolgreich_verteilt = False
                        break

                if erfolgreich_verteilt:
                    verteilte_kinder.extend(kinder_zur_verteilung)
                else:
                    kleine_gruppe.kinder = kinder_zur_verteilung  # Wiederherstellen
                    nicht_verteilbare_gruppen.append(kleine_gruppe)
                    alle_abgaenge_KINDER.append(kind)

            gruppen = andere_gruppen + nicht_verteilbare_gruppen

            # 2. Jetzt prüfen, ob Häuserzahl überschritten wird
            belegte_haeuser = len([g for g in gruppen if g.anzahl_kinder() > 0])
            ueberschuss = belegte_haeuser - max_haeuser

            if ueberschuss > 0:
                # Sortiere nach kleinster Gruppengröße zuerst (Auflösungspriorität)
                kandidaten = sorted(
                    [g for g in nicht_verteilbare_gruppen if g.anzahl_kinder() < min_kinder],
                    key=lambda g: g.anzahl_kinder()
                )

                abgaenge = []
                for g in kandidaten:
                    if belegte_haeuser <= max_haeuser:
                        break
                    abgaenge.extend(g.kinder)
                    gruppen.remove(g)
                    belegte_haeuser -= 1

                return gruppen, abgaenge

            return gruppen, []


        gruppen = []
        csv_daten = []
        altersdaten_pro_gruppe = []
     
        gruppenanzahl = {}
        durchschnitt_groesse = {}
        durchschnitt_alter = {}
        max_haeuser_pro_jahr = {}
        belegte_haeuser_pro_jahr = {}
        gesamt_angaenge = {}
        abgaenge_18 = {}
        abgaenge_kleine_gruppe = {}
        abgaenge_ueberschuss = {}
        abgaenge_prioritaet = {}
        Anzahl_Kinder = {}
        raum1_zähler ={}

        alle_Kinder = []  

        for jahr in range(STARTJAHR, STARTJAHR + ANZAHL_JAHRE):

            alle_abgaenge_KINDER = []
            gesamt_angaenge[jahr] = 0
            abgaenge_18[jahr] = 0
            raum1_zähler[jahr] = 0
            abgaenge_kleine_gruppe[jahr] = 0
            abgaenge_ueberschuss[jahr] = 0
            abgaenge_prioritaet[jahr] = 0

            max_haeuser = hole_wert_fuer_jahr(MAX_HAEUSER_PRO_JAHR, jahr, 999)
            neue_kinder_anzahl = hole_wert_fuer_jahr(NEUE_KINDER, jahr)
            kinder = []
            
            # Falls beobachtete Kinder für dieses Jahr vorhanden sind
            beobachtete_kinder = beobachteteGruppe.get(jahr, [])

            # 1. Neue Kinder aus der beobachteten Gruppe erzeugen
            anzahl_neu = 0
            for eintrag in beobachtete_kinder:
                if eintrag["Neu"]:
                    kind = Kind(Alter=eintrag["alter"], Eintrittsjahr=jahr, Namensbuchstabe=eintrag["namensbuchstabe:"])
                    kinder.append(kind)
                    alle_Kinder.append(kind)
                    anzahl_neu += 1

            # Reduziere das reguläre Kontingent
            verbleibende_neue_kinder = neue_kinder_anzahl - anzahl_neu

            # 2. Normale Kinder erzeugen (verteilt nach ALTER_VERTEILUNG)
            for alter, anteil in ALTER_VERTEILUNG.items():
                anzahl = int(verbleibende_neue_kinder * anteil)
                for _ in range(anzahl):
                    buchstabe = generiere_zufaelligen_buchstaben()
                    kind = Kind(Alter=alter, Eintrittsjahr=jahr, Namensbuchstabe=buchstabe)
                    kinder.append(kind)
                    alle_Kinder.append(kind)

            # 3. Füge „Neu = False“-Kinder hinzu: aus bestehenden Gruppen (z. B. zufällig)
            for eintrag in beobachtete_kinder:
                if not eintrag["Neu"]:
                    quellkinder = [k for g in gruppen for k in g.kinder if k.alter == eintrag["alter"]]
                    if quellkinder:
                        ausgewählt = random.choice(quellkinder)
                        neues_kind = Kind(Alter=ausgewählt.alter, Eintrittsjahr=jahr, Namensbuchstabe=eintrag["namensbuchstabe:"])
                        kinder.append(neues_kind)
                        alle_Kinder.append(neues_kind)


            random.shuffle(kinder)
            
            # Zähle geschlossene Gruppen (die mind. ein Kind mit 17 enthalten)
            raum1_zähler[jahr] = sum(1 for g in gruppen if any(k.alter == 17 for k in g.kinder))

            for gruppe in gruppen:
                alter_liste = [k.alter for k in gruppe.kinder]                
                if any(alter == 17 for alter in alter_liste):
                    gruppe.offen = False
                                        
                elif alter_liste and max(alter_liste) >= 18 and all(alter != 17 for alter in alter_liste):
                    gruppe.offen = True 
                    
            for gruppe in gruppen:
                gealterte_Kinder = []
                for kind in gruppe.kinder:
                    kind.alter += 1
                    if kind.alter >= 18:
                        abgaenge_18[jahr] += 1     
                        alle_abgaenge_KINDER.append(kind)                                    
                    else:
                        gealterte_Kinder.append(kind)
                gruppe.kinder = gealterte_Kinder
                           
            gesamt_angaenge[jahr] += abgaenge_18[jahr]

            # Entferne leere Gruppen sowieso
            gruppen = [g for g in gruppen if g.anzahl_kinder() > 0]

             # Entferne zu kleine Gruppen
            gruppen, abgaenge_kleine = verteile_und_entferne_kleine_gruppen(gruppen, MIN_KINDER, max_haeuser)

            abgaenge_kleine_gruppe[jahr] += len(abgaenge_kleine)
            gesamt_angaenge[jahr] += len(abgaenge_kleine)
   
            min_gruppen = hole_wert_fuer_jahr(MIN_NEUE_GRUPPEN_PRO_JAHR, jahr)
            aktuelle_gruppen = len(gruppen)
            fehlende_gruppen = max(0, min_gruppen - aktuelle_gruppen)

            neue_gruppen = [Gruppe() for _ in range(fehlende_gruppen)]
            gruppen.extend(neue_gruppen)

            kinder_zuweisen = kinder.copy()

            for gruppe in neue_gruppen:
                kinder_in_gruppe = []
                for kind in kinder_zuweisen:
                    if gruppe.offen and gruppe.hat_platz() and gruppe.altersspanne_ok(kind.alter):
                        gruppe.hinzufuegen(kind)
                        kinder_in_gruppe.append(kind)
                for kind in kinder_in_gruppe:
                    kinder_zuweisen.remove(kind)

            # Hier die Korrektur 1: abgaenge Block außerhalb der Schleife
            for kind in kinder_zuweisen:
                random.shuffle(gruppen)
                for gruppe in gruppen:
                    if gruppe.offen and gruppe.hat_platz() and gruppe.altersspanne_ok(kind.alter):
                        gruppe.hinzufuegen(kind)
                        break
                else:
                    neue_gruppe = Gruppe()
                    neue_gruppe.hinzufuegen(kind)
                    gruppen.append(neue_gruppe)

            abgaenge, max_haeuser, belegte_haeuser = berechne_anzahl_abgaenge(
                gruppen, jahr, MAX_HAEUSER_PRO_JAHR, 0.5
            )

         #   print(f"Jahr {jahr}: belegte Häuser = {belegte_haeuser}, max Häuser = {max_haeuser}, berechnete Abgänge = {abgaenge}")            
            max_haeuser_pro_jahr[jahr] = max_haeuser

            # Entferne initiale Abgänge
            if abgaenge > 0:
                gruppen = entferne_abgaenge_mit_prioritaet(
                    gruppen, abgaenge, PRIORITAETSALTER, restquote=PRIORITAETSALTER_RESTQUOTE,min_kinder=MIN_KINDER
                )
                abgaenge_prioritaet[jahr]+=abgaenge
                gesamt_angaenge[jahr] += abgaenge

            # Entferne leere Gruppen
            gruppen = [g for g in gruppen if g.anzahl_kinder() > 0]

            # Notfallreduktion, falls noch zu viele Gruppen
            versuche = 0
            max_versuche = 10

            abgaenge_nicht_verteilbar = []

            while len(gruppen) > max_haeuser and versuche < max_versuche:
                gruppen = [g for g in gruppen if g.anzahl_kinder() > 0]  # Leere Gruppen entfernen
                ueberschuss = len(gruppen) - max_haeuser

                # Neue Ergänzung: zu viele Gruppen gezielt auflösen
           #     print(f"⚠️ Jahr {jahr}: Trotz Reduktion noch {len(gruppen)} > {max_haeuser}. Löse {ueberschuss} kleinste Gruppen auf.")
                
                # Sortiere Gruppen nach Größe aufsteigend (kleinste zuerst)
                gruppen_sortiert = sorted(
                    [g for g in gruppen if g.offen],  # nur offene Gruppen!
                    key=lambda g: g.anzahl_kinder()
                )
                gruppen_aufloesen = gruppen_sortiert[:ueberschuss]

                # Entferne diese Gruppen
                for g in gruppen_aufloesen:
                    gruppen.remove(g)

                # Verteilt die Kinder der aufgelösten Gruppen neu
                kinder_zu_verteilen = []
                for g in gruppen_aufloesen:
                    kinder_zu_verteilen.extend(g.kinder)
                
                 
                for kind in kinder_zu_verteilen:
                    verteilt = False
                    for gruppe in gruppen:
                        if gruppe.offen and gruppe.hat_platz() and gruppe.altersspanne_ok(kind.alter):
                            gruppe.hinzufuegen(kind)
                            verteilt = True
                            break
                    if not verteilt:
                        abgaenge_nicht_verteilbar.append(kind)  
                   

                gruppen = [g for g in gruppen if g.anzahl_kinder() > 0]  # Leere Gruppen entfernen
                
                versuche += 1


            abgaenge_ueberschuss[jahr] += len(abgaenge_nicht_verteilbar)
            gesamt_angaenge[jahr] += len(abgaenge_nicht_verteilbar)
            belegte_haeuser_pro_jahr[jahr] = len(gruppen)

            # Sammle Statistik pro Jahr für CSV
            gruppenanzahl[jahr] = len(gruppen)
            gruppen_groessen = [g.anzahl_kinder() for g in gruppen]
            Anzahl_Kinder[jahr] = sum(gruppen_groessen)

            durchschnitt_groesse[jahr] = sum(gruppen_groessen) / gruppenanzahl[jahr] if gruppenanzahl[jahr] > 0 else 0
            durchschnitt_alter[jahr] = (
                sum(g.durchschnittsalter() * g.anzahl_kinder() for g in gruppen) / Anzahl_Kinder[jahr]
                if Anzahl_Kinder[jahr] > 0 else 0)

 #            print(f"Jahr {jahr}: Abgänge mit 18 = {abgaenge_18[jahr]}, Gesamtabgänge = {gesamt_angaenge[jahr]}")

            csv_daten.append({
                "Jahr": jahr,
                "Gruppenanzahl": gruppenanzahl.get(jahr),
                "Durchschnittliche Gruppengröße": durchschnitt_groesse.get(jahr, -1),
                "Durchschnittsalter": durchschnitt_alter.get(jahr, -1),
                "Maximale Hausanzahl": max_haeuser_pro_jahr[jahr],
                "Belegte Häuser": belegte_haeuser_pro_jahr[jahr],
                "Gesamtanzahl Abgänge": gesamt_angaenge[jahr],
                "Abgänge mit 18": abgaenge_18[jahr],
                "Abgänge wegen zu kleiner Gruppe": abgaenge_kleine_gruppe[jahr],
                "Abgänge wegen überschuss" :abgaenge_ueberschuss[jahr],
                "Abgänge priorisiert" : abgaenge_prioritaet[jahr],
                "Gesamtanzahl Kinder": Anzahl_Kinder[jahr],
                "Raum 1 Gruppen (ab Einer = 17)": raum1_zähler[jahr],
                "durchlauf": durchlauf_nummer,
            })

            for gruppen_id, gruppe in enumerate(gruppen):
                alters_zaehler = defaultdict(int)
                alters_kinder = defaultdict(list)

                for kind in gruppe.kinder:
                    alters_zaehler[kind.alter] += 1
                    alters_kinder[kind.alter].append(kind)
                for alter, kinder in alters_kinder.items():
                    verlauf_kinder[jahr][gruppen_id][alter] = kinder
                for alter, anzahl in alters_zaehler.items():
                    verlauf[jahr][gruppen_id][alter] = anzahl

            # Namensnummerierung nach Gruppenzuteilung erneuern
            for gruppe in gruppen:
                gruppe.vergebe_namensnummern()

            # Vorbereitung zur Beobachtungsstatus-Erkennung
            beobachtete_kinder_pro_jahr = {
                jahr: set(e["namensbuchstabe:"] for e in kinder)
                for jahr, kinder in beobachteteGruppe.items()
            }

            alle_kuenftig_beobachteten_buchstaben = {
                jahr: set.union(
                    *[beobachtete_kinder_pro_jahr[j]
                    for j in range(jahr + 1, STARTJAHR + ANZAHL_JAHRE)
                    if j in beobachtete_kinder_pro_jahr]
                ) if any(j > jahr for j in beobachtete_kinder_pro_jahr) else set()
                for jahr in range(STARTJAHR, STARTJAHR + ANZAHL_JAHRE)
            }

            # Altersdaten sammeln mit Beobachtungsstatus
            for jahr in verlauf:
                for gruppen_id in verlauf[jahr]:
                    for alter in verlauf[jahr][gruppen_id]:
                        anzahl = verlauf[jahr][gruppen_id][alter]
                        abgang = verlauf.get(jahr + 1, {}).get(gruppen_id, {}).get(alter + 1, 0)

                        gruppengroesse = sum(verlauf[jahr][gruppen_id].values())
                        kinder_in_diesem_alter = verlauf_kinder.get(jahr, {}).get(gruppen_id, {}).get(alter, [])

                        namenliste = [
                            k.get_Name() for k in kinder_in_diesem_alter
                            if hasattr(k, "namensbuchstabe") and k.namensbuchstabe
                        ]
                        namen_string = ";".join(namenliste)

                        # Beobachtungsstatus bestimmen
                        status = "nicht beobachtet"
                        buchstaben_in_gruppe = {k.namensbuchstabe for k in kinder_in_diesem_alter if k.namensbuchstabe}

                        if buchstaben_in_gruppe & beobachtete_kinder_pro_jahr.get(jahr, set()):
                            status = "beobachtet"
                        elif buchstaben_in_gruppe & alle_kuenftig_beobachteten_buchstaben.get(jahr, set()):
                            status = "zukünftig beobachtet"

                        altersdaten_pro_gruppe.append({
                            "jahr": jahr,
                            "gruppen_id": gruppen_id + 1,
                            "alter": alter,
                            "anzahl": anzahl,
                            "abgang_im_folgejahr": abgang,
                            "gruppen_groesse": gruppengroesse,
                            "max_altersspanne": maximale_altersspanne,
                            "belegte_haeuser": belegte_haeuser_pro_jahr.get(jahr, -1),
                            "max_haeuser": max_haeuser_pro_jahr.get(jahr, -1),
                            "durchlauf": durchlauf_nummer,
                            "namen": namen_string,
                            "beobachtungsstatus": status  # 🆕 Neue Spalte
                        })

            

        # Ergebnis speichern
        df_stat = pd.DataFrame(csv_daten)
        dateipfad_stat = os.path.join(ordnerpfad, f"simulation_stat_{maximale_altersspanne}_{maximale_gruppengroesse}_{durchlauf_nummer}.csv")
        df_stat.to_csv(dateipfad_stat, index=False)

        df_alter = pd.DataFrame(altersdaten_pro_gruppe)
        dateipfad_alter = os.path.join(ordnerpfad, f"simulation_alter_{maximale_altersspanne}_{maximale_gruppengroesse}_{durchlauf_nummer}.csv")
        df_alter.to_csv(dateipfad_alter, index=False)

        print(f"Simulation {durchlauf_nummer} abgeschlossen. Dateien gespeichert:")
        print(f" - Statistiken: {dateipfad_stat}")
        print(f" - Altersdaten: {dateipfad_alter}")

        return dateipfad_stat, dateipfad_alter

    except Exception as e:
        print(f"Fehler in der Simulation: {e}")
        raise


def merge_simulation_csvs(ordner):
    stat_files = glob(os.path.join(ordner, "simulation_stat_*.csv"))
    alter_files = glob(os.path.join(ordner, "simulation_alter_*.csv"))

    pfad_stat = None
    pfad_alter = None

    if not stat_files:
        print("⚠️ Keine Eingabedateien für Statistik gefunden!")
    else:
        gesamt_stat_df = pd.concat((pd.read_csv(f) for f in stat_files), ignore_index=True)
        pfad_stat = os.path.join(ordner, "gesamt_statistik.csv")
        gesamt_stat_df.to_csv(pfad_stat, index=False)

    if pfad_stat :
        print("✅ CSVs wurden zusammengeführt:")
        if pfad_stat:
            print(f" - {pfad_stat}")

    return pfad_stat

def kombiniere_csvs_zu_excel(ordner, auchAlter = True):
    ausgabe_excel = f"ausgabe_{ordner}.xlsx"
    excel_pfad = os.path.join(ordner, ausgabe_excel)

    pfad_stat  =  merge_simulation_csvs(ordner)

    if not os.path.exists(pfad_stat):
        print("❌ Zusammengeführte CSVs fehlen.")
        return

    if auchAlter:
        csv_dateien = glob(os.path.join(ordner, "simulation_alter_*.csv"))
      

    with pd.ExcelWriter(excel_pfad, engine="openpyxl", mode="w") as writer:
        if pfad_stat  is not None:
            pd.read_csv(pfad_stat).to_excel(writer, sheet_name="Statistik", index=False)
        if auchAlter:
            for datei in csv_dateien:
                try:
                    df = pd.read_csv(datei)
                    blattname = os.path.basename(datei).replace(".csv", "")
                    if len(blattname) > 31:
                        blattname = blattname[:31]
                    df.to_excel(writer, sheet_name=blattname, index=False)
                    print(f"\n✅ {blattname} in Datei {datei} eingelesen")
                except Exception as e:
                    print(f"❌ Fehler bei Datei {datei}: {e}")

    print(f"\n✅ Excel-Datei geschrieben: {excel_pfad}")


def ermittle_naechsten_ordnername(basisname):
    i = 1
    while True:
        ordnername = f"{basisname}{i}"
        if not os.path.exists(ordnername):
            return ordnername
        i += 1

def main():
    ordnerpfad_haeuser = ermittle_naechsten_ordnername("häuserplots")
    if not os.path.exists(ordnerpfad_haeuser):
        os.makedirs(ordnerpfad_haeuser)

    ordnerpfad_gruppen = ermittle_naechsten_ordnername("gruppenplots")
    if not os.path.exists(ordnerpfad_gruppen):
        os.makedirs(ordnerpfad_gruppen)

    MAX_GRUPPENGROESSE = 31
  
    parameter_kombinationen = [
        (4,   MAX_GRUPPENGROESSE,1)
        # (4, 31, 2),   
        # (4, 31, 3),   
        # (4, 31, 4),   
        # (4, 31, 5),   
        # (4, 31, 6),   
        # (4, 31, 7),     
        # (4, 31, 8),   
        # (4, 31, 9),   
        # (4, 31, 10),   
        # (4, 31, 11),   
        # (4, 31, 12),   
        # (4, 31, 13),   
        # (4, 31, 14),   
        # (4, 31, 15),   
    ]
    
    print(f"====================================={ordnerpfad_haeuser}=======================================")

    SEITENLÄNGE = 27.0

    MAX_HAEUSER_PRO_JAHR_DICT, aktiveHaeuserKoordinaten, beobachtetes_haus = berechne_haueser(
        SEITENLÄNGE,
        ordnerpfad_haeuser,
        True,
        2000,
    )

    max_zeit, zeiten_pro_bus, zeiten_beobachtet = simuliere_busfahrten(
        koordinaten=aktiveHaeuserKoordinaten[2000],
        anzahl_busse=16,
        wartezeit_pro_haus_sek=30,
        hinfahrt_kmh=40,
        rueckfahrt_kmh_schnell=100,
        rueckfahrt_schwelle_min=5,
        flaeche_seite=SEITENLÄNGE,
        beobachtetes_haus=beobachtetes_haus,
        plotte_Route = True,
        speicherordner=ordnerpfad_haeuser,
)


    print(f"Max-Zeit (Minuten): {max_zeit}")
    print(f"Zeiten pro Bus: {zeiten_pro_bus}")

    if zeiten_beobachtet:
        for bus_index, hin_min, rueck_min in zeiten_beobachtet:
            print(f"Beobachtetes Haus lag auf Route von Bus {bus_index}: Hin {hin_min} min, Rück {rueck_min} min")
    else:
        print("Das beobachtete Haus wurde von keinem Bus angefahren.")

    MAX_HAEUSER_PRO_JAHR =  konvertiere_jahresdict_zu_range_dict(  MAX_HAEUSER_PRO_JAHR_DICT )

    print(f"fertig: {ordnerpfad_haeuser}")
 
    print(f"====================================={ordnerpfad_gruppen}=======================================")


    ALTER_VERTEILUNG = {
            3: 0.1,
            4: 0.1,
            5: 0.1,
            6: 0.1,
            7: 0.1,
            8: 0.1,
            9: 0.1,
            10:0.1,
            11:0.1,
            12:0.1,            
        }

    MIN_NEUE_GRUPPEN_PRO_JAHR, NEUE_KINDER = ermittle_minimale_gruppen_und_kinder(
        offset_KINDERFAKTOR = 1.3,
        MAX_HAEUSER_PRO_JAHR=MAX_HAEUSER_PRO_JAHR,    
        maximale_gruppengroesse = MAX_GRUPPENGROESSE,
        alter_verteilung=ALTER_VERTEILUNG
)

 
    argumente = [(param[0], param[1], param[2],  ordnerpfad_gruppen, MAX_HAEUSER_PRO_JAHR,  MIN_NEUE_GRUPPEN_PRO_JAHR, NEUE_KINDER,ALTER_VERTEILUNG) for param in parameter_kombinationen]


    with ProcessPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
        ergebnisse = list(executor.map(simuliere_gruppen, argumente))

    print("Alle Simulationen abgeschlossen. CSVs werden kombiniert.")
    kombiniere_csvs_zu_excel(ordnerpfad_gruppen,True)
    print(f"fertig: {ordnerpfad_gruppen}")

    print(f"====================================={ordnerpfad_gruppen}=======================================")

if __name__ == "__main__":
  #  print("Logger wird initialisiert")
  #  logger = LogManager('meinlog_Komplett.log', extra_logfile='meinLog_letzterDurchlauf.log')
    main()