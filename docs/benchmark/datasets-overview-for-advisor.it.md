# Dataset aperti per il benchmark semi-sintetico: quadro per la discussione

Preparato il 2026-10-06 per l'incontro di progetto. Progetto: estensione del paper "Clinical Pathways as Safety Specifications for Physical AI in Hospital Wards" in una submission a IEEE RA-L. La validazione è tecnica e pre-clinica: nessun paziente reale, nessuna affermazione clinica.

Tutti i fatti qui sotto sono stati letti dai file in `data/raw/` e dalle pagine dei dataset su PhysioNet e VitalDB il 2026-10-06. Nulla è citato a memoria. **Non sono ancora verificati da una persona** nel senso del piano (`docs/benchmark/public-sources.md`, sezione "Verification status"): le righe su licenze e mappature richiedono ancora un `verified_by`.

Versione inglese (convenzione del repo): `docs/benchmark/datasets-overview-for-advisor.md`.

## 1. Perché servono dati esterni

Il benchmark è generato, non registrato (`docs/plan/workstreams/WS04-benchmark/README.md`). Un paziente virtuale riceve una traccia latente di pressione, un processo di aderenza, una risposta al farmaco, e poi un processo di misura che trasforma la giornata latente in quella osservata, l'unica che i monitor vedono. Guasti (C2) e attacchi (C3) si iniettano sul lato osservato. La ground truth si calcola sulla traccia latente e i monitor non la leggono mai.

I dati reali servono a due cose soltanto:

1. **Realismo dei segnali osservati diversi dalla pressione**: frequenza cardiaca, SpO2 e rumore ECG reale per il guasto C2 `ecg_noise`.
2. **Prior clinici** (risposta al farmaco, variabilità tra pazienti, soglie): serve MIMIC-IV, che richiede credenziali e **per ora non è disponibile**.

Nessun dataset pubblico contiene dati di dispenser smart, quindi l'aderenza resta un'ipotesi dichiarata.

## 2. Cosa è stato scaricato

Tutto sotto `data/raw/`, ignorato da git, mai committato, mai ridistribuito. Scaricato il 2026-10-05.

| Dataset | Versione | Licenza (come dichiarata nella pagina del dataset) | Accesso | Spazio su disco | Controllo di integrità |
|---|---|---|---|---|---|
| MIT-BIH Noise Stress Test (NSTDB) | 1.0.0 | Open Data Commons Attribution 1.0 | libero | 68 MB | `SHA256SUMS.txt` ufficiale, 97 voci, tutte corrette |
| BIDMC PPG and Respiration | 1.0.0 | Open Data Commons Attribution 1.0 | libero | 209 MB | `SHA256SUMS.txt` ufficiale, 483 voci, tutte corrette |
| PhysioNet/CinC Challenge 2015 (set di addestramento) | 1.0.0 | Open Data Commons Attribution 1.0 | libero | 741 MB (ZIP più copia estratta) | checksum ufficiali di `training/` corretti; ZIP e file di licenza con checksum calcolato in locale |
| VitalDB (**sottoinsieme: 30 casi su 6.388** più i file di metadati) | 1.0.0 su PhysioNet | **vedi sezione 8, punto 1** | libero | 585 MB | 36 voci (30 casi, licenza, 5 file di metadati), tutte corrette |

Non scaricati: MIT-BIH Arrhythmia Database (non serve, vedi NSTDB) e i dataset con credenziali MIMIC-IV, MIMIC-IV-ED ed eICU-CRD (vedi sezione 5).

## 3. Cosa contiene ogni dataset e se possiamo usarlo

Il generatore legge tre tipi di segmento (`src/ralmon/benchmark/segments.py`): `hr_clean`, `spo2_clean` e `hr_error_ecg_noise` (errore della frequenza cardiaca causato dal rumore ECG, per il guasto C2).

### 3.1 MIT-BIH Noise Stress Test: da usare, per il guasto C2 `ecg_noise`

| Parametro | Valore |
|---|---|
| Registrazioni | 15: 12 ECG con rumore aggiunto (`118e*`, `119e*`) e 3 di solo rumore |
| Segnali | derivazioni ECG MLII e V1 (registrazioni ECG); due canali di rumore (registrazioni di rumore) |
| Campionamento | 360 Hz; 30 min per registrazione (1806 s) |
| Registrazioni di solo rumore | `bw` oscillazione della linea di base, `ma` artefatto muscolare, `em` movimento degli elettrodi |
| Livello di rumore (SNR) | 24, 18, 12, 6, 0, -6 dB, una registrazione per livello e per soggetto |
| Andamento del rumore | inizia dopo i primi 5 min; alterna 2 min con rumore e 2 min puliti |
| Fonte del rumore nelle registrazioni miste | solo `em` |
| Battiti di riferimento | annotazioni `.atr` copiate dagli originali puliti, quindi i battiti veri sono noti anche dove il tracciato è illeggibile |
| Soggetti | 2 (record 118 e 119 del MIT-BIH Arrhythmia Database) |

**Perché usarlo.** L'errore della frequenza stimata da un rilevatore QRS rispetto alle annotazioni di riferimento è una traccia di errore da rumore reale, con sei livelli di intensità e un andamento intermittente naturale. Copre il requisito di almeno tre magnitudini di guasto (WS04-T07). L'aggiunta del MIT-BIH Arrhythmia Database, proposta nel piano, non è necessaria.

**Limiti.** Solo due soggetti. Le registrazioni miste contengono solo rumore `em`; `bw` e `ma` dovremmo aggiungerli noi. Rumore ambulatoriale, non di reparto. Va scelto e dichiarato un rilevatore QRS nella nota di estrazione.

### 3.2 BIDMC PPG and Respiration: da usare come fonte secondaria per frequenza cardiaca e SpO2, e per l'errore della frequenza di polso

| Parametro | Valore |
|---|---|
| Registrazioni | 53 pazienti di terapia intensiva, 8 min ciascuno (circa 7 h in totale) |
| Valori numerici, 1 Hz | HR (da ECG), PULSE (da pletismografia), RESP, SpO2 |
| Forme d'onda, 125 Hz | RESP, PLETH, II in tutti i 53; V (49), AVR (47), CVP (10), ABP (8), I, MCL, ART, III |
| Altro | annotazioni manuali dei respiri; età, sesso, reparto; id di origine in MIMIC-II |
| Valori misurati | HR p5/p50/p95 = 67/89/115 bpm; SpO2 = 92/98/100 %; 132 righe numeriche mancanti su 25.493 |
| Pazienti | età da 19 a 90+ (una mancante); 32 F, 20 M, 1 non indicato |

**Perché usarlo.** HR e SpO2 reali, al periodo di campionamento voluto dal generatore. HR e PULSE sono registrati negli stessi istanti, come i nostri `hr_ecg` e `hr_pulse`, quindi la loro differenza dà una stima empirica dell'errore della frequenza di polso, oggi un parametro vuoto.

**Limiti.** In tutto circa 7 h contro 1.400 giorni-paziente: bisognerebbe ricucire i segmenti, e ogni cucitura è una discontinuità che il report di validazione deve dichiarare (`join_count`). Pazienti di terapia intensiva, più gravi di quelli di reparto. Il valore dell'errore di polso sarebbe una proposta da far approvare a una persona (ADR-020).

### 3.3 VitalDB: da usare per frequenza cardiaca e SpO2, eventualmente per l'errore del bracciale; non per la farmacologia

Il dataset completo ha 6.388 casi chirurgici e 196 tracce. Noi abbiamo 30 casi.

| Parametro | Valore |
|---|---|
| Valori numerici del monitor (`Solar8000`, 44) | HR, PLETH_HR, PLETH_SPO2, NIBP_SBP/DBP/MBP (bracciale), ART_SBP/DBP/MBP (invasiva), CVP, temperatura, ETCO2, frequenza respiratoria, livelli ST, valori del ventilatore |
| Forme d'onda (`SNUADC`) | ART, CVP, ECG_II, ECG_V5, FEM, PLETH, tutte a 500 Hz |
| Altri dispositivi | macchina d'anestesia (37 tracce), pompe di infusione (51: nitroglicerina, nitroprussiato, diltiazem, vasopressori, propofol, remifentanil, altri), profondità dell'anestesia (8), ossimetria cerebrale (2), gittata cardiaca (4 dispositivi), riscaldatore di fluidi (7) |
| Tabella clinica | 6.388 casi, 74 colonne: età, sesso, BMI, classe ASA, reparto, `preop_htn`, esami preoperatori, totali intraoperatori |
| Dataset completo | età p5/p50/p95 = 30/59/78 anni; **1.965 casi con `preop_htn` = 1**; reparti: chirurgia generale 4.930, toracica 1.111, ginecologia 230, urologia 117 |
| I nostri 30 casi | durata mediana 3,5 h (da 0,8 a 8,7 h); HR, SpO2 ed ECG in 30/30; pressione col bracciale in 26; pressione invasiva in 18; **bracciale e invasiva insieme in 14** |
| Cadenza del bracciale nei nostri casi | mediana di 17,5 valori distinti per caso; circa un nuovo valore ogni 2,5 min (nostra stima dai cambi di valore) |

**Perché usarlo.**
- *HR e SpO2*: i segmenti durano ore, quindi molte meno cuciture che con BIDMC. Sono disponibili migliaia di casi e la scelta si può restringere ai pazienti ipertesi.
- *Errore del bracciale*: la differenza bracciale meno invasiva nei 14 casi che hanno entrambe le misure dà una stima empirica del parametro vuoto `cuff_error_sd`. Attenzione: la linea invasiva ha un proprio errore e i pazienti sono anestetizzati.

**Perché non per la farmacologia.** I farmaci sono endovenosi e intraoperatori. Non ci sono dosi orali di antipertensivi, e la nitroglicerina compare in 1 solo dei nostri 30 casi.

**Limiti.** Pazienti anestetizzati e ventilati: HR e SpO2 sono più stabili e spostati rispetto a un reparto. Va dichiarato come limite.

### 3.4 PhysioNet/CinC Challenge 2015: da usare solo come riferimento esterno per il carico di allarmi

| Parametro | Valore |
|---|---|
| Registrazioni | 750 di addestramento, 250 Hz, da 300 a 330 s attorno a un allarme |
| Segnali | II (728), V (684), PLETH (627), ABP (343), RESP (278), alcuni altri |
| Etichette | 294 allarmi veri e 456 falsi (61% falsi) |
| Per tipo di allarme (veri / falsi) | asistolia 22/100; bradicardia 46/43; tachicardia 131/9; flutter o fibrillazione ventricolare 6/52; tachicardia ventricolare 89/252 |

**Perché usarlo.** Un riferimento reale di quanto spesso gli allarmi dei monitor commerciali sono falsi, per inquadrare l'alarm fatigue (osservazione dei revisori R3-W6, regola di reporting onesto H9).

**Limiti.** Le registrazioni sono ritagliate attorno agli allarmi, non sono monitoraggio continuo: non se ne ricava un numero di alert per giorno-paziente, e la quota di falsi riflette la selezione della challenge. I loro allarmi di aritmia sono cosa diversa dai nostri alert sul care plan. Non fornisce segmenti al benchmark.

## 4. Riepilogo dell'uso

| Esigenza del generatore | Fonte | Stato |
|---|---|---|
| `hr_error_ecg_noise` (C2 `ecg_noise`) | NSTDB | utilizzabile ora |
| `hr_clean`, `spo2_clean` | VitalDB (meglio i casi ipertesi), BIDMC come secondaria | utilizzabile ora |
| Errore della frequenza di polso | BIDMC | utilizzabile ora, il valore richiede approvazione |
| `cuff_error_sd` | VitalDB, facoltativo | utilizzabile ora, il valore richiede approvazione |
| Riferimento sul carico di allarmi | CinC 2015 | utilizzabile ora, solo come confronto |
| Risposta al farmaco (PK/PD), variabilità tra pazienti, valori di base, finestra di risposta | MIMIC-IV | **bloccato: nessun accesso con credenziali** |
| Analogo del dispenser (tabella `pyxis`) | MIMIC-IV-ED | bloccato, stessa ragione |
| Shift di distribuzione reale per l'ablazione A6 | eICU-CRD | bloccato, stessa ragione; A6 resta solo sintetica |
| Aderenza | nessuna | ipotesi dichiarata |
| Contenuto clinico del pathway template (bande, soglie, finestre, farmaco) | nessun dataset: linea guida e scheda tecnica, ancorate da un clinico | **bloccato: serve la revisione clinica (WS00-T07)**, vedi sezione 7 |
| Care plan dei pazienti virtuali | generati dal builder a partire dal template | sintetici per costruzione, vedi sezione 7 |

## 5. Cosa i dati pubblici non ci danno

Ogni parametro clinico, fisiologico e di dispositivo del generatore è ancora vuoto: tutte le 17 righe di `configs/priors/literature_hypertension.yaml` sono `awaiting_human_value` e 17 nomi del registro clinico sono `unset`. Il piano vieta a un agente di scegliere questi valori (ADR-020): ogni numero ricavato da questi dataset è quindi una proposta con una regola di estrazione documentata, da far approvare a una persona.

Finché non esiste l'accesso a MIMIC, tutti i risultati sono etichettati "semi-sintetico, prior da letteratura" (ADR-005, regola H6). I dataset con credenziali richiedono inoltre il corso CITI e un data use agreement. Questo può vietare l'invio di dati a livello di riga a servizi esterni: in tal caso agli agenti arriverebbero solo aggregati.

## 6. A che punto è il codice

- WS04-T06 (processo di misura, libreria dei segmenti) è integrato. Legge i file dei segmenti da `data/raw/segments/`, che **non esiste ancora**: nessun segmento è stato estratto. Senza, il benchmark si costruisce con `allow_no_segments=True` e senza campioni di HR o SpO2.
- WS04-T07 (iniezione C2) è in corso su un altro branch.
- Gli artefatti umani WS00-T04 (registro delle credenziali) e WS00-T09 (licenze, versioni e checksum dei dataset) sono segnati come fatti, ma i loro file non esistono. Questo documento e gli esiti dei checksum qui sopra coprono parte del contenuto di T09; manca ancora la conferma di una persona.

## 7. Clinical pathway e care plan: dataset o generazione?

**Non esiste un dataset di clinical pathway da scaricare, e il benchmark non ne ha bisogno.** Il pathway è l'input del sistema, cioè la specifica da monitorare, non un dato da imparare. I care plan dei pazienti virtuali si possono generare in modo sintetico. Il contenuto clinico del template invece non si può né inventare né ricavare da un dataset.

### 7.1 I due livelli

Il progetto distingue due livelli (glossario in `CLAUDE.md`):

- **Pathway template** (livello istituzionale, per l'ipertensione): i 7 template STL RANGE, SCHED, HOLD, COUNT, RESP, SYS, INT (`docs/formal/02-templates.md`, sezione 3.1). I loro parametri stanno nel registro clinico: banda di pressione, soglia di hold, finestra di risposta Δ1/Δ2, massimo di dosi e così via.
- **Patient care plan** (`CarePlan`): l'istanza del template per un paziente, con le istanze dei template e gli orari di misura e somministrazione.

| Livello | Da dove viene | Può essere arbitrario? |
|---|---|---|
| Contenuto clinico del template (bande, soglie, finestre, farmaco) | linea guida e scheda tecnica di un farmaco, ancorate da un clinico (WS00-T03 e T07, ADR-020) | No. Nessun agente sceglie valori o farmaci e nessun dataset li fornisce. |
| Care plan dei 200 pazienti virtuali | il builder (WS04-T11) li istanzia dal template, dal registro e dal paziente estratto | Sì. È sintetico per costruzione. |
| Ground truth | si calcola valutando le formule del piano sulla traccia latente | Non serve annotare nulla a mano. |

### 7.2 Stato attuale e un rischio

`configs/benchmark/care_plans.yaml` contiene oggi due dosi (07:00 e 21:00) e 5 misure al giorno, entrambe con `dist: null` e marcate `illustrative_unverified` (dall'esempio dell'analisi). Il registro clinico `configs/registry/hypertension.yaml` è `unreviewed`.

**Rischio:** con questa configurazione tutti i 200 pazienti avrebbero lo stesso piano, e il benchmark proverebbe un piano solo, non la generalizzazione tra piani. Il registro prevede override per paziente, ma solo dentro range approvati dal clinico (`docs/formal/03-parameter-registry.md`, sezione 5), e nella versione 0.1.0 sono vuoti. Si può variare senza rischi ciò che non è clinico (orari delle dosi, numero di misure) come `design_choice`. Le soglie si variano solo con range approvati.

### 7.3 Dataset che aiutano, ma come statistiche

Nessuno contiene pathway formalizzati con vincoli temporali.

- **MIMIC-IV (eMAR):** il piano lo indica per le somministrazioni di antipertensivi (`docs/plan/workstreams/WS04-benchmark/README.md`, tabella delle fonti). Darebbe orari e frequenze reali per rendere realistica la variabilità dei piani. Richiede le credenziali e la struttura delle tabelle è ancora da verificare.
- **eICU-CRD:** la sua pagina dichiara "care plan documentation" tra i contenuti, ma non ne abbiamo verificato la struttura. Lo si vede solo dopo l'accesso.
- **FHIR PlanDefinition e CarePlan:** non è un dataset, ma uno standard. Il piano prevede uno schizzo di mapping verso i nostri template (WS01-T07). L'analisi (§3.4) lo indica come punto forte e poco costoso, perché risponde alla critica che i template non derivano da una rappresentazione standard.

### 7.4 Il punto aperto per il paper

L'abstract in bozza dice che i template coprono "[M] di [M′] vincoli di [due] care pathway rivisti da clinici" (`docs/source/analisi.md`, bozza di abstract). Per sostenerlo servono uno o due documenti di pathway reali o pubblici, per esempio un protocollo ospedaliero o una linea guida. Da lì si elencano i vincoli (M′) e si mostra quali i template esprimono (M). È un piccolo corpus costruito a mano, non un dataset. Nei file di piano che abbiamo controllato (INDEX, README di WS01, master plan) non risulta un task che lo procuri.

### 7.5 Approccio proposto

1. Un solo pathway di ipertensione (ADR-001), ancorato dal clinico a un farmaco e a una linea guida.
2. Piani dei pazienti generati con variabilità negli orari e nel numero di misure, e con override clinici solo dove approvati.
3. Un documento di pathway pubblico o ospedaliero come base per il conteggio M/M′ e per il mapping FHIR.

## 8. Decisioni e input richiesti

1. **Licenza di VitalDB.** La copia su PhysioNet dichiara CC BY 4.0. Il data use agreement del sito ufficiale dichiara CC BY-NC-SA 4.0. Quale vale per noi, e la clausola non commerciale con condivisione alle stesse condizioni limita la ridistribuzione dei segmenti derivati nella release open source (WS13)?
2. **Credenziali PhysioNet per MIMIC-IV, MIMIC-IV-ED ed eICU-CRD.** Chi detiene l'account e il corso CITI è stato fatto? È l'unica via verso prior clinici reali e verso un test di shift reale.
3. **Regola di estrazione dei segmenti.** Approvare o correggere la proposta: frequenza di riferimento dalle annotazioni NSTDB contro frequenza dal rilevatore QRS per `hr_error_ecg_noise`; casi ipertesi di VitalDB per `hr_clean` e `spo2_clean`; BIDMC come fonte secondaria e per l'errore di polso. Vanno nominati un criterio di "pulito" e il rilevatore.
4. **Errore del bracciale.** Ricaviamo `cuff_error_sd` da VitalDB (bracciale contro invasiva) o dallo standard del dispositivo? Nel file dei prior è citato l'ISO 81060-2, con "edizione e clausola da confermare".
5. **Numero di casi VitalDB.** 30 bastano per controllare la pipeline. Quanti ne vogliamo per la release, data la dimensione dell'insieme completo (circa 95 GB su PhysioNet)? L'API di VitalDB permette di scaricare singoli casi.
6. **Revisione clinica.** Il registro clinico e i 17 prior richiedono un clinico (WS00-T07) prima che un risultato possa perdere l'etichetta "non verificato".
7. **Quanti pathway.** I "[due]" pathway dell'abstract sono due farmaci o protocolli per l'ipertensione, oppure due patologie? Nel secondo caso entra il diabete (WS04-T14, opzionale) e cambia il carico di lavoro.
8. **Variabilità dei care plan.** Approvare che orari delle dosi e numero di misure variino tra pazienti come `design_choice`, lasciando le soglie cliniche fisse finché il clinico non approva dei range per gli override.
9. **Corpus di pathway.** Quale documento (protocollo ospedaliero o linea guida pubblica) usiamo per il conteggio M/M′, chi lo fornisce, e chi estrae i vincoli? Va deciso anche se affidare lo schizzo di mapping FHIR a WS01-T07.

## 9. Promemoria sul perimetro

Solo validazione tecnica e pre-clinica. Nessun dataset qui è usato per affermazioni su pazienti reali. I dataset aperti alimentano il realismo dei segnali della traccia osservata. Non alimentano la risposta della pressione al trattamento.
