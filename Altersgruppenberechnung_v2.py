from collections import defaultdict
from itertools import product
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import os
import pandas as pd
from glob import glob
import random
from log_manager import LogManager


def hole_wert_fuer_jahr(zuordnung, jahr, standardwert=0):
    for zeitraum, wert in zuordnung.items():
        if jahr in zeitraum:
            return wert
    return standardwert

def fuehre_simulation_aus(argumente):
    try:
        maximale_altersspanne, maximale_gruppengroesse, durchlauf_nummer, ordnerpfad = argumente
        print(f"Starte Simulation mit: Altersspanne={maximale_altersspanne}, Gruppengröße={maximale_gruppengroesse}, Lauf={durchlauf_nummer}")

        STARTJAHR = 1970
        ANZAHL_JAHRE = 50

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
            range(1970, 1975): 10,
            range(1975, 1980): 20,
            range(1980, 1990): 50,
            range(1990, 2000): 75,
            range(2000, 2020): 100,
        }

        NEUE_KINDER = {
            range(1970, 1975): 50,
            range(1975, 1980): 100,
            range(1980, 1990): 500,
            range(1990, 2000): 750,
            range(2000, 2020): 1000,
        }

        MAX_HAEUSER_PRO_JAHR = {
            range(1970, 1971): 10,
            range(1971, 1972): 20,
            range(1972,1973): 30,
            range(1973, 1974): 40,
            range(1974, 1975): 50,
            range(1975, 1976): 75,
            range(1976, 1977): 100,
            range(1977, 1980): 125,
            range(1980, 1985): 150,
            range(1985, 1990): 175,
            range(1990, 2005): 384,            
            range(2005, 2020): 1472,       
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

        verlauf = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

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

            for alter, anteil in ALTER_VERTEILUNG.items():
                anzahl = int(neue_kinder_anzahl * anteil)
                kinder.extend([Kind(alter) for _ in range(anzahl)])
                neue_kinder = [Kind(alter) for _ in range(anzahl)]
                alle_Kinder.extend(neue_kinder)

            random.shuffle(kinder)
            
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

            raum1_zähler[jahr] = sum(1 for g in gruppen if not g.offen)

            print(f"Jahr {jahr}: Abgänge mit 18 = {abgaenge_18[jahr]}, Gesamtabgänge = {gesamt_angaenge[jahr]}")

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
                for kind in gruppe.kinder:
                    alters_zaehler[kind.alter] += 1
                for alter, anzahl in alters_zaehler.items():
                    verlauf[jahr][gruppen_id][alter] = anzahl


            for jahr in verlauf:
                for gruppen_id in verlauf[jahr]:
                    for alter in verlauf[jahr][gruppen_id]:
                        anzahl = verlauf[jahr][gruppen_id][alter]
                        abgang = verlauf.get(jahr + 1, {}).get(gruppen_id, {}).get(alter + 1, 0)

                         # Neue Zeile: Gruppengröße ermitteln
                        gruppengroesse = sum(verlauf[jahr][gruppen_id].values())

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

def kombiniere_csvs_zu_excel(ordner):
    ausgabe_excel = f"ausgabe_{ordner}.xlsx"
    excel_pfad = os.path.join(ordner, ausgabe_excel)

    pfad_stat  =  merge_simulation_csvs(ordner)

    if not os.path.exists(pfad_stat):
        print("❌ Zusammengeführte CSVs fehlen.")
        return

   # csv_dateien = glob(os.path.join(ordner, "simulation_alter_*.csv"))
    csv_dateien = []

    with pd.ExcelWriter(excel_pfad, engine="openpyxl", mode="w") as writer:
        if pfad_stat  is not None:
            pd.read_csv(pfad_stat).to_excel(writer, sheet_name="Statistik", index=False)
        # for datei in csv_dateien:
        #     try:
        #         df = pd.read_csv(datei)
        #         blattname = os.path.basename(datei).replace(".csv", "")
        #         if len(blattname) > 31:
        #             blattname = blattname[:31]
        #         df.to_excel(writer, sheet_name=blattname, index=False)
        #         print(f"\n✅ {blattname} in Datei {datei} eingelesen")
        #     except Exception as e:
        #         print(f"❌ Fehler bei Datei {datei}: {e}")

    print(f"\n✅ Excel-Datei geschrieben: {excel_pfad}")


def ermittle_naechsten_ordnername(basisname="plots"):
    i = 1
    while True:
        ordnername = f"{basisname}{i}"
        if not os.path.exists(ordnername):
            return ordnername
        i += 1

def main():
    ordnerpfad = ermittle_naechsten_ordnername()
    if not os.path.exists(ordnerpfad):
        os.makedirs(ordnerpfad)

    print(f"====================================={ordnerpfad}=======================================")

    parameter_kombinationen = [
        (4, 31, 1),     
        (4, 31, 2),   
        (4, 31, 3),   
        (4, 31, 4),   
        (4, 31, 5),   
        (4, 31, 6),   
        (4, 31, 7),     
        (4, 31, 8),   
        (4, 31, 9),   
        (4, 31, 10),   
        (4, 31, 11),   
        (4, 31, 12),   
        (4, 31, 13),   
        (4, 31, 14),   
        (4, 31, 15),   
    ]

    argumente = [(param[0], param[1], param[2], ordnerpfad) for param in parameter_kombinationen]

    with ProcessPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
        ergebnisse = list(executor.map(fuehre_simulation_aus, argumente))

    print("Alle Simulationen abgeschlossen. CSVs werden kombiniert.")
    kombiniere_csvs_zu_excel(ordnerpfad)
    print(f"fertig: {ordnerpfad}")
   
    print(f"====================================={ordnerpfad}=======================================")

if __name__ == "__main__":
  #  print("Logger wird initialisiert")
  #  logger = LogManager('meinlog_Komplett.log', extra_logfile='meinLog_letzterDurchlauf.log')
    main()