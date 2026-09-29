# Analisi del paper "Clinical Pathways as Safety Specifications for Physical AI in Hospital Wards" in vista di una submission RA-L

*Paper analizzato: workshop paper IJCAI-ECAI 2026, workshop "Safe Robotics in the Era of Physical AI" (Franchini, Mallardi, De Carolis, Lanubile). Target: special issue IEEE RA-L, 6 pagine. Documento generato il 16 settembre 2026.*

## Indice

1. Sintesi: cosa il paper afferma e cosa dimostra davvero
2. Simulazione di review RA-L (R1, R2, R3, meta-review AE)
3. Novità e posizionamento
4. Rigore tecnico e coerenza interna
5. Piano sperimentale realistico
6. Contributi rivisti
7. Struttura proposta per le 6 pagine
8. Qualità della scrittura (titoli e abstract proposti)
9. Roadmap prioritaria
10. Rischi residui

Nel testo uso tre etichette. **[FATALE]** indica un problema che da solo porta al reject. **[MAGGIORE]** indica un problema da major revision o da revise-and-resubmit. **[MINORE]** indica un problema che si corregge in una revisione minore. Le sezioni del paper sono citate come §II-B.c, §III-A e così via.

---

## 1. Sintesi: cosa il paper afferma e cosa dimostra davvero

1. **Tesi.** I Clinical Pathways possono essere riletti come specifiche di sicurezza verificabili a runtime per un sistema robotico assistivo in reparto. Il paper propone un'architettura a tre livelli: sensing, robot con Runtime Safety Monitor (RSM), cloud.
2. **Proposta.** L'RSM combinerebbe forecasting, conformal prediction e monitoring STL robusto. Emetterebbe alert ⟨τ, κ, σ, ρ, ξ⟩ classificati in C1 (deviazioni fisiologiche), C2 (guasti) e C3 (tampering).
3. **Cosa è dimostrato.** Nulla, né in senso formale né in senso empirico. Mancano formule STL scritte, algoritmi, proposizioni, implementazione e dati. La Tabella I è costruita a mano e dichiarata non valutativa.
4. **Cosa è solo proposto, e in parte incoerente.** La codifica di φ_CP, la normalizzazione di σ, la definizione di ρ, il meccanismo di κ, la distinzione tra guasto e tampering, il valore aggiunto del robot come canale ridondante.
5. **Contributo reale.** Un framing ben motivato e una position. Per RA-L equivale a una proposta di ricerca, non a un risultato. L'estensione deve costruire quasi tutto il contenuto tecnico da zero.

---

## 2. Simulazione di review RA-L

### R1: Runtime verification e formal methods

**Summary.** Gli autori propongono di usare i Clinical Pathways come specifiche STL monitorate online su un robot assistivo. La semantica robusta servirebbe a ordinare gli alert per severità, e un livello conforme ne modulerebbe la confidenza. Il contributo è descritto solo a parole: non c'è alcuna specifica formale.

**Punti di forza.**
1. Il passaggio da anomaly detection a specification-based monitoring è ben argomentato e coerente con la letteratura RV per CPS.
2. Tenere l'authoring della specifica sotto governance clinica, con il robot che valuta ma non modifica, è una scelta architetturale sensata.
3. Gli autori riconoscono (§II-B.b) che ♢[Δ1,Δ2] impedisce verdetti immediati, cioè il problema della monitorabilità.

**Debolezze.**
1. **[FATALE] Nessuna formula.** §II-B.a dice che i vincoli "can be encoded in STL" e che φ_CP "is structured as a conjunction of these constraint patterns", ma non scrive una sola formula. Il contributo 1 ("reformulation of Clinical Pathways as runtime-verifiable safety specifications") non è quindi verificabile. Mancano sintassi, segnali, predicati e almeno un template completo del running example.
2. **[MAGGIORE] Semantica robusta non definita e citata male.** L'unico riferimento STL è Maler & Nickovic 2004, che definisce la semantica booleana. Mancano i lavori che introducono la robustness quantitativa. Soprattutto, σ(φ₁∧φ₂) = min(σ₁, σ₂) su predicati in mmHg, secondi e conteggi è definito matematicamente ma privo di significato. Il claim "allows the RSM to rank alerts by severity" (§II-B.b) non regge, e la Tabella I lo conferma con −12 (mmHg), −21 (secondi?) e −8 (unità ignota).
3. **[MAGGIORE] Predicati booleani.** Per PILL sollevato a segnale indicatore, la robustness spaziale è degenere (±1 o ±∞) e non esprime alcun "margine". Per i vincoli di timing serve la time robustness, che il paper non menziona.
4. **[MAGGIORE] Campionamento sparso e irregolare.** Cinque misure di pressione al giorno contro una semantica a tempo denso. Non si dice come si interpola né come si trattano eventi puntuali. "□φ … at every evaluation step" (§II-B.b) presuppone un tempo discreto mai definito.
5. **[MAGGIORE] Espressività sottostimata e sovrastimata insieme.**
   - "measurable pressure decrease" richiede di riferirsi a un valore passato, quindi un operatore di freeze oppure un segnale derivato.
   - I "sequence constraints" richiedono operatori past o until.
   - Nessuna delle due esigenze è discussa.
   - I contatori sono dichiarati "outside STL" e gestiti da "windowed counters", ma possono essere predicati STL su segnali derivati. Tenendoli fuori dalla logica si perde l'uniformità di σ e ξ.
6. **[MAGGIORE] Online monitoring non risolto.** §II-B.b rimanda il problema di ♢ alla "pipeline below", ma la pipeline (§II-B.c) non definisce semantica a tre valori, robustness interval o riscrittura past-time. La Tabella I emette a 21:02 un verdetto cross-modale che, con la semantica dichiarata, può essere emesso solo dopo le 22:02 (vedi §4.6).
7. **[MAGGIORE] Soundness temporale.** Timestamp dei dispositivi BLE, clock skew, messaggi fuori ordine e latenza di trasporto non sono discussi. Per vincoli con finestre di minuti sono determinanti.
8. **[MAGGIORE] φ_HW e φ_DOSE compaiono solo nella caption della Tabella I.** Un vincolo di "hardware-liveness" non deriva dal Clinical Pathway. Il claim "A single monitor handles all three classes" (§III-A) confonde specifica clinica e specifica di sistema.
9. **[MINORE]** L'integrità della specifica distribuita al robot (firma, versioning) non è trattata.
10. **[MINORE]** Nessun tool (RTAMT, Breach, S-TaLiRo), nessuna complessità, nessun cenno a RV per ROS.

**Domande agli autori.**
1. Potete scrivere φ_CP completo per lo scenario di ipertensione?
2. Quale robust semantics usate (spatial, time, averaged), e come rendete confrontabili unità diverse dentro min e max?
3. Come è calcolato σ = +18 alle 07:00, quando la finestra di risposta al farmaco è ancora aperta?
4. Come esprimete "decrease" rispetto a un valore pre-dose?
5. Come gestite timestamp e ordinamento degli eventi provenienti dai dispositivi BLE?

**Raccomandazione: Reject.** Il contributo centrale dichiarato è formale, ma il paper non contiene formalizzazione. Gli unici numeri presenti (Tabella I) sono incoerenti con la semantica descritta.

### R2: Machine learning e uncertainty quantification

**Summary.** Il paper propone un predittore di serie temporali avvolto da conformal prediction, i cui intervalli dovrebbero decidere quando una violazione STL va segnalata. Una confidenza ρ accompagnerebbe ogni alert. Non vengono specificati modello, dati, score, calibrazione o risultati.

**Punti di forza.**
1. Tenere separate severità e confidenza è un'intuizione utile.
2. Gli autori riconoscono in §IV che l'exchangeability è violata attorno agli eventi clinici.

**Debolezze.**
1. **[FATALE] Predittore inesistente come oggetto tecnico.** Non si sa cosa predice, con quali input, su quale orizzonte, addestrato su quali dati. Non c'è alcuna valutazione.
2. **[MAGGIORE] Contraddizione interna in §II-B.c.** Si legge che "violations are flagged only when the uncertainty envelope exits the STL-defined safe region" e poco dopo che "final safety verdicts remain grounded in CP-defined events and measured values". Se il verdetto si basa sul valore misurato, non è chiaro su cosa agisca l'inviluppo conforme: sulla misura, sulla previsione o sulla robustness? Inoltre, segnalare solo quando l'inviluppo è interamente fuori dalla regione sicura è la scelta anti-conservativa per la safety, perché riduce la recall proprio sui casi al confine.
3. **[MAGGIORE] ρ ∈ [0,1] non definito.** La conformal prediction produce insiemi con coverage marginale, non una confidenza per singolo alert. In Tabella I, ρ = 0.42 per un contatore deterministico mostra la confusione tra incertezza sulla violazione e incertezza sull'autenticità o sulla causa.
4. **[MAGGIORE] Unità di exchangeability e coverage.** Non si dice se si calibra su time step (non scambiabili) o su episodi paziente, né quanti episodi di calibrazione servono. La coverage marginale sulla popolazione non è coverage per il singolo paziente. Molti test ripetuti (vincoli × istanti × pazienti) generano falsi allarmi: manca un controllo per giorno-paziente.
5. **[MAGGIORE] Previsione della pressione tra misure sparse.** Con cinque misure al giorno, un forecast a qualche ora avrà intervalli conformi così larghi da non uscire mai dalla regione sicura. Stimare la pressione da ECG e PPG è il problema della cuffless BP, notoriamente poco affidabile. La componente predittiva rischia di essere inutile proprio sul segnale del running example.
6. **[MAGGIORE] Aggiornamenti dei modelli.** "periodic model updates pushed back to the RSM" (§II-A) invalida la calibrazione se non si ricalibra su dati held-out a ogni aggiornamento.
7. **[MAGGIORE] Tampering come "low confidence".** §III-A afferma che gli eventi C3 "surface as low confidence on otherwise plausible-looking signals". Ma rumore, distribution shift e guasti producono anch'essi ρ basso: il segnale non è identificabile. Manca un modello avversario.
8. **[MINORE]** "A multivariate time-series learner predicts physiological trajectories against which observed values are compared" è di fatto residual-based anomaly detection, cioè ciò da cui il paper dichiara di volersi allontanare.
9. **[MINORE]** "the time-series learner provides robust evaluation under noise" (§IV) non è supportato.

**Domande agli autori.**
1. Qual è la nonconformity score, e l'unità di calibrazione è il paziente o il time step?
2. Potete dare una definizione matematica di ρ e dire quale garanzia offre?
3. Come controllate il tasso di falsi allarmi per giorno-paziente?
4. Come vi comportate sotto distribution shift (reparto contro dati di training, singolo paziente contro popolazione)?
5. Ricalibrate dopo ogni aggiornamento dal cloud?

**Raccomandazione: Reject.** La componente di uncertainty quantification è nominata ma non specificata. Le due affermazioni chiave (verdetti "grounded in measured values" e uso dell'inviluppo conforme) sono tra loro in contraddizione.

### R3: Healthcare robotics e HRI clinica

**Summary.** Un robot assistivo (TIAGo Pro) raggiunge il paziente secondo il pathway, supervisiona le misure e ospita un monitor che segnala deviazioni cliniche, guasti e manomissioni. Lo scenario è l'ipertensione. Non ci sono esperimenti, coinvolgimento di clinici o analisi dei rischi.

**Punti di forza.**
1. Il problema è rilevante: aderenza al piano di cura, carico sul personale infermieristico, auditabilità degli alert.
2. La governance clinica della specifica è una scelta corretta.
3. I limiti in §IV sono dichiarati con onestà, in particolare "establishes feasibility, not efficacy".

**Debolezze.**
1. **[FATALE] Nessuna validazione.** Non c'è simulazione, laboratorio, dataset o parere clinico. L'abstract ("to assist nursing staff in real-world hospital wards") promette ciò che il paper non mostra.
2. **[FATALE per RA-L] Il ruolo del robot non è giustificato, e l'architettura ha un difetto strutturale.**
   - L'RSM gira sul robot e riceve stream BLE (§II-A). Quando il robot lascia la stanza, per portata radio o per servire un altro paziente, gli stream cadono.
   - Un robot per N pazienti non può essere il percorso unico del monitoraggio.
   - Se il robot si guasta o si scarica, il monitoraggio si ferma: "every alert goes through a single auditable verification path" è un single point of failure.
   - Non si dice chi monitora il monitor.
   - Senza una risposta a questi punti, un reviewer chiederà cosa aggiunge il robot rispetto a un bedside monitor con gateway fisso.
3. **[MAGGIORE] Terminologia clinica.** Un Clinical Pathway è normalmente un piano di cura strutturato a livello istituzionale per una popolazione di pazienti. Orari, dosi e bande per il singolo paziente sono una prescrizione o un care plan. I parametri (risposta in 1–3 h, banda 110–140 mmHg) non sono ancorati a un farmaco né a una linea guida: onset e picco variano di ore tra le diverse molecole antipertensive.
4. **[MAGGIORE] Tassonomia clinicamente fuorviante.**
   - Un'apertura del dispenser non programmata due minuti dopo quella regolare (21:02) è molto più probabilmente un doppio prelievo del paziente, cioè un errore di terapia clinicamente rilevante, oppure un rimbalzo del sensore (C2). Classificarla come tampering è discutibile.
   - Bloccare il dispenser dopo il fatto non mitiga nulla, e bloccare i farmaci è di per sé un hazard.
   - "Missed measurements at scheduled times" è classificato C1 "physiological", ma è una deviazione di processo spesso causata da C2, per esempio il robot che non arriva.
5. **[MAGGIORE] Rischi introdotti dal robot.** Collisioni, infection control, privacy della camera RGB-D nelle stanze. Inoltre la presenza non equivale all'identità: "verifies presence via its RGB-D stack" non protegge dagli errori di paziente. Manca qualsiasi riferimento a risk management (ISO 14971) o a standard per robot di cura personale (ISO 13482).
6. **[MAGGIORE] Workflow degli alert.** Non si sa chi li riceve, attraverso quale canale, con quale escalation, né con quale carico atteso di falsi allarmi (alarm fatigue). La "intrinsic explainability" di una sub-formula STL non è comprensibile a un infermiere senza una resa in linguaggio naturale e una verifica con utenti.
7. **[MINORE] Imprecisioni.**
   - "patient-worn Bluetooth devices (… smart pill dispenser)": il dispenser non è indossato.
   - Un "wearable sphygmomanometer" 24 ore su 24 va specificato come dispositivo per monitoraggio ambulatoriale della pressione.
   - "ambient sensors" compaiono nel testo ma non in Fig. 1.
   - "middleware-agnostic" (§II-A) contrasta con la dipendenza dagli stati lifecycle ROS 2 (INACTIVE, §III-B).

**Domande agli autori.**
1. Cosa succede al monitoraggio quando il robot esce dalla stanza o si guasta?
2. Quale farmaco e quale linea guida fondano Δ1, Δ2 e la banda pressoria?
3. Un doppio prelievo del paziente come verrebbe classificato?
4. Chi ha validato la tassonomia dal punto di vista clinico?
5. Qual è il carico atteso di alert per turno?

**Raccomandazione: Reject**, con incoraggiamento a ripresentare. La motivazione è buona, ma per una rivista di robotica mancano validazione, analisi dei rischi e una giustificazione dell'embodiment.

### Meta-review dell'Associate Editor

I tre reviewer concordano sul valore del framing: monitorare l'aderenza al piano di cura invece di stimare anomalie statistiche è una prospettiva utile per la safety dei sistemi robotici clinici. Concordano anche su quattro problemi, ciascuno sufficiente per il reject.

1. Assenza di qualsiasi validazione sperimentale.
2. Assenza di formalizzazione: φ_CP, ρ e κ non sono definiti.
3. Novità non posizionata rispetto alla letteratura esistente su STL con conformal prediction, sulla formalizzazione delle linee guida cliniche e sul monitoring di medical CPS.
4. Contributo robotico debole: il robot è un host del monitor, non una parte necessaria della soluzione.

A questi si aggiungono incoerenze interne che minano la credibilità: σ con unità incomparabili, verdetto cross-modale temporalmente impossibile in Tabella I, contraddizione tra verdetti misurati e inviluppo conforme, classificazione C3 non identificabile.

**Decisione: Reject.** Una versione estesa sarebbe valutabile se contenesse:
- una specifica formale completa con semantica online definita;
- definizioni operative di σ normalizzato, ρ e κ;
- un modello esplicito di guasti e attacchi;
- una valutazione quantitativa contro baseline ragionevoli, incluso il metodo più vicino in letteratura;
- evidenza che l'embodiment contribuisce misurabilmente.

---

## 3. Novità e posizionamento

**Nota sui riferimenti.** Per ogni riferimento indico autori, anno e venue come li ricordo. Vanno tutti verificati su DBLP o Google Scholar prima di citarli. Con (†) segno quelli su cui ho incertezza specifica su venue, anno o elenco autori. Dove non ho un riferimento affidabile lo dico esplicitamente, invece di costruirlo.

### 3.1 Runtime monitoring STL per robotica e CPS

**Cosa si aspetta il reviewer.**
- Semantica robusta: Fainekos & Pappas (Theoretical Computer Science, 2009); Donzé & Maler (FORMATS 2010), dove compare anche la time robustness.
- Algoritmi di monitoring: Donzé, Ferrère & Maler (CAV 2013).
- Online monitoring con robustness interval su tracce parziali: Deshmukh et al. (RV 2015, versione estesa su Formal Methods in System Design 2017).
- Survey: Bartocci et al., "Specification-based monitoring of cyber-physical systems" (Lectures on Runtime Verification, LNCS 10457, 2018); Leucker & Schallhart (JLAP 2009).
- Semantica a tre valori: Bauer, Leucker & Schallhart (ACM TOSEM 2011).
- Tool: RTAMT, Ničković & Yamaguchi (ATVA 2020).
- RV in ROS: ROSRV di Huang et al. (†, SIMPAR 2014); ROSMonitoring di Ferrando et al. (†, TAROS 2020).
- Verifica formale in robotica: survey di Luckcuck et al. (ACM Computing Surveys 2019).
- Runtime assurance: SOTER, Desai et al. (DSN 2019); architettura Simplex (Sha, 2001).
- Normalizzazione e pesatura: AGM robustness di Mehdipour, Vasile & Belta (†, CDC 2019); weighted STL (†, stessi autori).
- Freeze: STL* di Brim et al. (†, Information and Computation 2014).
- Time robustness per il controllo: Rodionova et al. (†, CDC 2021).

**Differenza.** Il vostro contributo non può essere l'algoritmo di monitoring, che esiste. Può essere tre cose:
- la classe di specifiche (template derivati da piani di cura) su segnali clinici sparsi, irregolari e misti continuo/evento;
- una severità normalizzata con scale cliniche;
- l'accoppiamento tra specifica clinica e task del robot.

**Rischio: ALTO** se il claim resta "usiamo STL robusto per la safety a runtime". Un reviewer di formal methods lo liquiderebbe come applicazione di RTAMT.

### 3.2 Conformal prediction applicata a STL e a sistemi con predittori appresi

**Cosa si aspetta il reviewer.**
- Il lavoro più vicino al vostro: Lindemann, Qin, Deshmukh & Pappas, "Conformal prediction for STL runtime verification" (ICCPS 2023).
- Predictive monitoring: Bortolussi, Cairoli, Paoletti et al., "Neural predictive monitoring" (RV 2019 e versione estesa su STTT, †); Cairoli, Paoletti & Bortolussi, conformal quantitative predictive monitoring di requisiti STL (†, HSCC 2023).
- Distribution shift: Zhao, Hoxha, Fainekos, Deshmukh & Lindemann, robust conformal prediction per STL runtime verification (†, ICCPS 2024).
- Conformal in robotica: Lindemann et al., "Safe planning in dynamic environments using conformal prediction" (IEEE RA-L 2023). Essendo su RA-L, va citato.
- Conformal su serie temporali: Stankeviciute, Alaa & van der Schaar (NeurIPS 2021); Xu & Xie, EnbPI (ICML 2021).
- Non-exchangeability: Gibbs & Candès, adaptive conformal inference (NeurIPS 2021); Barber, Candès, Ramdas & Tibshirani, "Conformal prediction beyond exchangeability" (Annals of Statistics 2023); Angelopoulos, Candès & Tibshirani, conformal PID control (NeurIPS 2023).

**Differenza possibile.**
- Campionamento sparso ed event-driven, anziché traiettorie dense.
- Separazione esplicita tra verdetto su dati misurati e verdetto predittivo.
- Calibrazione per episodio paziente, con variante adattiva per il singolo paziente.
- Integrazione con attribuzione della causa.

**Rischio: MOLTO ALTO.** La frase dell'abstract "combines temporal prediction, uncertainty-aware reasoning, and constraint-based verification" descrive quasi esattamente Lindemann et al. 2023. Se non citate quel lavoro e non lo usate come baseline, R1 o R2 lo faranno per voi, e il reject per mancanza di novità diventa probabile.

### 3.3 Specification-based monitoring in ambito medico

**Cosa si aspetta il reviewer.**
- Medical CPS: Lee, Sokolsky et al., "Challenges and research directions in medical cyber-physical systems" (Proceedings of the IEEE 2012); Arney et al., closed-loop medical device systems (†, ICCPS 2010).
- Generic PCA infusion pump: Kim et al. (†, EMSOFT 2011).
- Pacemaker e modelli cardiaci: Jiang, Pajic & Mangharam (†, Proceedings of the IEEE 2012).
- Pancreas artificiale e runtime safety: Cameron, Fainekos, Maahs & Sankaranarayanan (†, RV 2015).
- STL per la ventilazione assistita in terapia intensiva: Bufo, Bartocci, Bortolussi et al. (†, ISoLA 2014).
- Shape expressions con esempi ECG: Ničković et al. (†, RV 2019).
- Falsi allarmi: PhysioNet/Computing in Cardiology Challenge 2015 sui falsi allarmi aritmici in terapia intensiva (Clifford et al., CinC 2015).
- Alarm fatigue: Sendelbach & Funk (AACN Advanced Critical Care 2013); Drew et al. (PLoS ONE 2014).
- Early warning score: NEWS2 (Royal College of Physicians, 2017).
- Limiti dei modelli ML di deterioramento: Wong et al., validazione esterna di un modello proprietario di predizione della sepsi (JAMA Internal Medicine 2021). È utile per motivare l'approccio specification-based.

**Differenza.** Quei lavori monitorano un dispositivo, un controllore o una singola proprietà fisiologica. Voi monitorate l'aderenza a un processo di cura che coinvolge più dispositivi, il paziente e un agente robotico, e attribuite la causa della violazione.

**Rischio: MEDIO.** Il monitoring basato su specifiche in ambito medico non è nuovo. La novità sta nella scala del processo e nell'attribuzione.

### 3.4 Formalizzazione di clinical guidelines e clinical pathways

**Cosa si aspetta il reviewer.**
- Confronto tra formalismi: Peleg et al., "Comparing computer-interpretable guideline models" (JAMIA 2003).
- Formalismi: GLIF, Ohno-Machado et al. (JAMIA 1998); PROforma, Fox, Johns & Rahmanzadeh (AI in Medicine 1998); Asbru, nel progetto Asgaard di Shahar, Miksch & Johnson (AI in Medicine 1998); GLARE, Terenziani et al. (†, AI in Medicine 2001).
- Temporal abstraction: Shahar, knowledge-based temporal abstraction (Artificial Intelligence 1997).
- Model checking di linee guida: progetto Protocure, ten Teije et al. (†, AI in Medicine 2006); Bottrighi et al. (†, AI in Medicine 2010).
- Monitoring dichiarativo con semantica su tracce finite (Declare): Maggi, Montali, Westergaard & van der Aalst (†, BPM 2011).
- Conformance di linee guida con SCIFF: filone Chesani, Mello, Montali et al. (†, verificate il lavoro specifico).
- Process mining in sanità: Mans, van der Aalst & Vanwersch (SpringerBriefs 2015); Rojas et al. (Journal of Biomedical Informatics 2016); Munoz-Gama et al. (JBI 2022).
- Conformance checking: Carmona et al. (Springer 2018); online conformance checking, Burattin et al. (†, BPM 2018).
- BPMN per pathways: BPMN4CP, Braun et al. (†, 2014).
- Standard: HL7 FHIR PlanDefinition e CarePlan, Clinical Quality Language, Arden Syntax, openEHR GDL.

**Differenza.** Questi approcci lavorano su eventi discreti del record clinico, spesso offline, per decision support o conformance retrospettiva. Voi lavorate su segnali continui, con robustness quantitativa, online e su un agente embodied.

**Rischio: ALTO sul contributo 1.** Asbru esprime già intenzioni e condizioni temporali monitorabili durante l'esecuzione, e il monitoring online di vincoli di processo clinico con logiche temporali esiste. "Reinterpret CPs as runtime safety specifications" non può essere venduto come idea nuova. Va riposizionato come passaggio a monitoring quantitativo a livello di segnale, eseguito da un agente fisico. È forte, e poco costoso, mostrare anche parzialmente un mapping da una rappresentazione standard (FHIR PlanDefinition o BPMN) ai vostri template.

### 3.5 Robot assistivi in reparto

**Cosa si aspetta il reviewer.**
- Panoramiche: Riek, "Healthcare robotics" (Communications of the ACM 2017); Yang et al., ruolo della robotica durante COVID-19 (Science Robotics 2020); Kyrarini et al., survey sui robot in sanità (†, Technologies 2021).
- Studi sul campo con robot logistici ospedalieri: Ljungblad et al. (†, CSCW 2012).
- Coordinamento delle cure assistito da robot: Gombolay et al. (†, RSS 2016 e IJRR).
- TIAGo in contesti assistivi: progetto ENRICHME, Coşar et al. (†, International Journal of Social Robotics 2020).
- Verifica formale di robot di cura: Dixon, Webster et al. (†, TAROS 2014); Webster et al. (†, IEEE Transactions on Human-Machine Systems 2016).
- Robot commerciali da reparto come Moxi: non ho un riferimento peer-reviewed affidabile, verificate voi se esistono studi pubblicati.
- Standard: ISO 13482, ISO 14971, IEC 62304.

**Differenza.** La letteratura si concentra su logistica, accettazione e verifica del comportamento del robot a design-time. Voi proponete il monitoraggio a runtime dell'aderenza al piano di cura, con il robot come esecutore di task vincolati dalla specifica e come fonte di evidenza.

**Rischio: BASSO sulla novità, ALTO sulla domanda "perché serve un robot?"**.

### 3.6 Sicurezza e tampering di dispositivi medici indossabili

**Cosa si aspetta il reviewer.**
- Attacchi a dispositivi: Halperin et al., pacemaker e ICD (IEEE S&P 2008); Li, Raghunathan & Raghunathan, "Hijacking an insulin pump" (†, Healthcom 2011).
- Survey: Rushanan et al., SoK su dispositivi impiantabili e body area network (IEEE S&P 2014); Camara, Peris-Lopez & Tapiador (†, JBI 2015).
- Vulnerabilità BLE: SweynTooth, Garbelini et al. (†, USENIX ATC 2020).
- Rilevamento con invarianti fisiche o fisiologiche: Rostami, Juels & Koushanfar, Heart-to-Heart (†, CCS 2013); Choi et al., control invariants per veicoli robotici (†, CCS 2018); Shoukry et al., PyCRA (†, CCS 2015).
- Diagnosabilità: Sampath et al., "Diagnosability of discrete-event systems" (IEEE TAC 1995).
- Regolatorio: guidance FDA sulla cybersecurity dei dispositivi medici nelle premarket submission (2023).

**Differenza.** Usate invarianti derivati dalla specifica clinica (cross-modali) e un testimone embodied, invece di crittografia o probing attivo del sensore.

**Rischio: ALTO.** Senza threat model, un reviewer di sicurezza obietterà che un attaccante informato può iniettare dati fisiologicamente plausibili e cross-modalmente coerenti, non rilevabili per costruzione. Il claim C3 va ridimensionato a "integrity/plausibility violations" contro classi di attacco dichiarate.

### 3.7 Claim di novità difendibile

Presi singolarmente, i quattro ingredienti esistono: STL monitoring, conformal prediction, formalizzazione dei pathway e robot assistivi. Un claim difendibile per RA-L è la combinazione verificata sperimentalmente di tre elementi, nessuno dei quali è coperto dal metodo più vicino:

1. template STL derivati da piani di cura, su segnali clinici sparsi e misti, con severità normalizzata clinicamente;
2. verdetti a tre valori che separano formalmente l'evidenza misurata dalla previsione conforme;
3. un livello di attribuzione che usa l'embodiment come canale di evidenza, di cui si misura il contributo.

---

## 4. Rigore tecnico e coerenza interna

### 4.1 Formalizzazione STL [FATALE nella versione attuale]

Il paper non contiene nessuna formula: φ_CP è citato cinque volte e mai definito. Serve una sezione "Problem Formulation" con quattro elementi.

1. **Segnali.** Per esempio: bp(t) ultimo valore misurato, piecewise-constant; m(t) indicatore di misura; d(t) indicatore di erogazione; s(t) tick di schedulazione; c_d(t) conteggio di erogazioni in (t−24h, t]; h_c(t) salute del nodo del bracciale; q(t) durata di gonfiaggio; w(t) presenza o assunzione osservata dal robot.
2. **Semantica di campionamento.** Tempo discreto con periodo del monitor T_s, interpolazione piecewise-constant, eventi come impulsi di un campione.
3. **Template.** Una tabella con formula, unità della robustness e scala di normalizzazione.
4. **Scomposizione.** φ = φ_CP ∧ φ_SYS ∧ φ_INT, invece di chiamare φ_CP anche i vincoli di sistema.

Esempio di template per il running example. I valori numerici sono illustrativi e vanno ancorati a farmaco e linea guida.

```latex
% Care-plan constraints (phi_CP), past-time formulations monitorable without look-ahead
\varphi_{\mathrm{range}} = \square\,\big(m \rightarrow (bp \ge 110 \wedge bp \le 140)\big)
\varphi_{\mathrm{sched}} = \square\,\big(\mathrm{O}_{[W,W]}\, s \rightarrow \mathrm{O}_{[0,W]}\, m\big)
\varphi_{\mathrm{hold}}  = \square\,\big(d \rightarrow \mathrm{O}_{[0,60\,\mathrm{min}]}\,(m \wedge bp \ge 100)\big)
\varphi_{\mathrm{count}} = \square\,\big(c_d \le 2\big) \;\wedge\; \square\,\big(e_{\mathrm{day}} \rightarrow c_d \ge 2\big)
\varphi_{\mathrm{resp}}  = \square\,\big(\mathrm{O}_{[\Delta_2,\Delta_2]}\, d \rightarrow \mathrm{O}_{[0,\Delta_2-\Delta_1]}\,(m \wedge r \ge \delta)\big),
\quad r(t) = bp^{\mathrm{pre}}(t) - bp(t)
% System constraints (phi_SYS) and integrity constraints (phi_INT)
\varphi_{\mathrm{SYS}} = \square\,\big(m \rightarrow (h_c = 1 \wedge q \ge q_{\min})\big)
\varphi_{\mathrm{INT}} = \square\,\big(d \rightarrow \mathrm{O}_{[0,5\,\mathrm{min}]}\,(w \vee a_{\mathrm{auth}})\big)
```

Cinque aspetti vanno discussi esplicitamente nel paper.

1. **Riferimento pre-dose.** "Pressure decrease" richiede un riferimento al valore prima della dose. Si ottiene con un segnale derivato bp^pre calcolato dal livello di signal abstraction, che resta dentro STL standard, oppure con un operatore di freeze (STL*). Il segnale derivato è più semplice ed è supportato dai tool.
2. **Contatori.** Non sono "outside STL": c_d(t) è un segnale derivato e c_d ≤ 2 un predicato atomico con robustness 2 − c_d (in dosi). Così σ e ξ restano uniformi.
3. **Hold parameter.** φ_hold ("non somministrare se la pressione sistolica è sotto soglia") è un vincolo di sequenza reale e clinicamente molto credibile. Mostra perché servono gli operatori past, ed è un esempio migliore di quelli attuali.
4. **Obbligo di misura nella finestra.** φ_resp è soddisfacibile solo se una misura cade in [t+Δ1, t+Δ2]. La specifica clinica induce quindi un obbligo di task per il robot. Questo è il ponte naturale verso il contributo robotico, e va detto.
5. **Eventi puntuali.** O_[W,W] su impulsi richiede allineamento al campionamento. In pratica serve O_[W, W+T_s], da dichiarare.

### 4.2 Unità di σ e normalizzazione [MAGGIORE]

Il problema non riguarda solo l'ordinamento degli alert. La robustness stessa di φ_CP, come congiunzione, è un min su quantità in mmHg, minuti e dosi, quindi è semanticamente vuota. Inoltre, per i predicati su segnali booleani la robustness spaziale è degenere. Per vincoli di timing (φ_sched, φ_resp) usate la time robustness, in secondi o minuti.

**Soluzione raccomandata**, in tre passi.

1. **Normalizzazione per predicato:** σ̃_π = clip(σ_π / s_π, −1, 1). La scala s_π è la deviazione clinicamente significativa, fissata con un clinico (per esempio 20 mmHg, 30 min, 1 dose) e riportata nella tabella dei template. Dopo la normalizzazione, min e max hanno senso.
2. **Ordinamento lessicografico tra classi:** prima la priorità clinica del template (per esempio φ_hold > φ_range > φ_sched), assegnata dal clinico, poi σ̃ all'interno della stessa priorità. Non si ordina un −0.6 di timing contro un −0.6 pressorio come se fossero equivalenti.
3. **Alternative da citare:** AGM robustness e weighted STL, che richiedono comunque predicati normalizzati. Oppure la mappatura su bande ordinali stile NEWS2.

Va evitato di normalizzare con l'ampiezza dell'intervallo conforme, stile z-score: mescolerebbe severità e incertezza, esattamente ciò che il paper vuole tenere separato.

### 4.3 Predittore, conformal e verdetti misurati: la contraddizione [MAGGIORE]

In §II-B.c convivono due letture incompatibili.

- **Lettura A, predictive monitoring.** Il predittore completa la traccia futura e la conformal prediction limita l'errore sulla robustness predetta. Il verdetto riguarda il futuro.
- **Lettura B, incertezza di misura.** Il verdetto riguarda il valore misurato, e la conformal prediction non ha ruolo.

La frase "violations are flagged only when the uncertainty envelope exits the STL-defined safe region" aggiunge un terzo problema: se applicata ai valori misurati, sopprime i veri positivi vicino alla soglia.

**Soluzione:** separare formalmente i due canali in un verdetto a tre valori, trattato in §4.7.

- Il verdetto definitivo si calcola solo dal prefisso misurato, con robustness interval. L'incertezza di misura è modellata dall'errore del dispositivo, non dal predittore.
- La previsione conforme entra solo nello stato PENDING e produce early warning, mai verdetti definitivi.

Così la frase "final safety verdicts remain grounded in measured values" diventa vera per costruzione, e il predittore ha un ruolo preciso.

C'è anche un suggerimento strategico. La pressione con cinque misure al giorno è un pessimo candidato per la previsione, perché gli intervalli sarebbero enormi. Candidati molto migliori per la componente predittiva sono i segnali continui (frequenza cardiaca, SpO₂) e soprattutto le deadline di care delivery del robot: prevedere che il robot arriverà tardi alla finestra delle 21:00, dati coda di task e navigazione, e allertare l'infermiere prima. È predictive monitoring conforme su un problema genuinamente robotico, e rafforza il fit con RA-L.

### 4.4 Definizione operativa di ρ [MAGGIORE]

ρ = 0.42 per un contatore deterministico rivela che ρ viene usato per due cose diverse:
- (i) quanto è certo che il vincolo sia violato;
- (ii) quanto è certo che l'evento sia autentico o dovuto a una certa causa.

La (ii) appartiene all'attribuzione κ. Proposta di definizione per tipo di verdetto:

| Tipo di verdetto | Definizione di ρ | Garanzia |
|---|---|---|
| Violazione misurata su predicato continuo | ρ = P(σ_vero < 0 \| misura), con modello d'errore del dispositivo. Esempio: errore gaussiano con deviazione standard dai protocolli di validazione del bracciale; per bp = 152 e soglia 140, ρ = Φ(12/s_dev) | Condizionata all'adeguatezza del modello d'errore, da dichiarare |
| Violazione predetta | Score one-sided R = σ − σ̂ calibrato su episodi paziente. Si emette PREDICTED-VIOLATION se σ̂ + q₁₋α < 0 e si pone ρ = 1 − α*, con α* = inf{α : σ̂ + q₁₋α < 0}, che è una sorta di p-value conforme | Marginale: P(alert emesso ∧ σ ≥ 0) ≤ α sotto exchangeability tra episodi |
| Predicato deterministico su log di eventi (contatori) | ρ = 1 | Condizionata all'integrità del log; l'autenticità dell'evento va in κ |

La garanzia della seconda riga discende in poche righe dal quantile conforme one-sided. È una proposizione piccola ma nuova nel vostro setting, e dà a R1 e R2 qualcosa di formale da verificare. Tre avvertenze vanno esplicitate nel testo:
- l'unità di calibrazione è l'episodio paziente, non il time step;
- la coverage è marginale sulla popolazione, non condizionata al paziente;
- con molti test per giorno-paziente serve un'allocazione di α, altrimenti i falsi allarmi crescono linearmente.

Due soglie danno inoltre un trade-off esplicito:
- "likely violation" quando σ̂ + q < 0, che limita i falsi allarmi;
- "possible violation" quando σ̂ − q < 0, che limita le violazioni mancate.

La scelta tra le due va motivata clinicamente.

### 4.5 κ: con quale meccanismo si distinguono C1, C2 e C3? [MAGGIORE]

Oggi κ non è prodotto da nessun modulo: non compare in Fig. 1 né nella pipeline. Il testo suggerisce che derivi dalla sub-formula violata, ma allora C2 è riconosciuto solo perché φ_HW è violata, il che è circolare, e C3 si basa su "low confidence", che non è identificabile (§III-A).

Il nodo di fondo è l'identificabilità. Una erogazione senza successiva riduzione della pressione è compatibile con almeno quattro cause:
- tampering (C3);
- farmaco non assunto o sputato (deviazione clinica o di aderenza);
- non-risposta farmacologica (C1);
- sensore di pressione guasto (C2).

La sola sub-formula non può distinguerle. Serve un livello di attribuzione esplicito su un vettore di evidenze.

1. **Provenienza del verdetto:** se è violata una sub-formula di φ_CP, φ_SYS o φ_INT.
2. **Salute del sistema:** stati lifecycle ROS 2, diagnostics, liveliness e deadline QoS, metriche del link BLE, batteria, esito dei task di navigazione e manipolazione.
3. **Qualità del segnale:** signal quality index per ECG e PPG, codici d'errore del bracciale.
4. **Coerenza tra dispositivi.** Per esempio la frequenza di polso riportata dal bracciale contro la frequenza cardiaca da ECG nello stesso istante: è una ridondanza gratuita e molto convincente.
5. **Testimone embodied:** presenza, identità e assunzione osservate dal robot, quando è presente.
6. **Provenienza crittografica e temporale:** autenticazione dei messaggi, numeri di sequenza, plausibilità dei timestamp, rilevamento di replay.

Come regola decisionale suggerisco di partire da regole gerarchiche con astensione, che sono auditabili:
- evidenza di integrità → C3;
- altrimenti evidenza di sistema → C2;
- altrimenti violazione clinica con canali coerenti → C1;
- evidenze conflittuali o insufficienti → **UNDETERMINED**.

Una variante probabilistica (rete bayesiana con probabilità stimate sul benchmark) che produca p_κ è opzionale. La classe UNDETERMINED è essenziale: senza di essa ogni errore di attribuzione diventa un errore di classificazione non dichiarato.

Nel paper includerei una **matrice di diagnosabilità**. Esempio da raffinare:

| Evento reale | Evidenza discriminante | Distinguibile? |
|---|---|---|
| Ipertensione reale (C1) | Violazione di φ_range con tutti i canali coerenti | Sì, per esclusione |
| Non-risposta farmacologica (C1) | Violazione di φ_resp; assunzione vista dal robot o autenticata dal dispenser | Solo se c'è un testimone |
| Bracciale staccato, guasto evidente (C2) | Codice d'errore, durata di gonfiaggio anomala, cambio di stato del nodo | Sì |
| Bracciale con bias o deriva silenziosa (C2) | Nessun canale indipendente sulla pressione; la frequenza di polso resta coerente | **No**: limite da dichiarare |
| Robot in ritardo alla finestra (C2) | Violazione di φ_sched ed esito del task di navigazione | Sì |
| Doppio prelievo del paziente (deviazione di aderenza) | Violazione di φ_count, variazione di peso o conteggio pillole | Sì, se il dispenser misura il contenuto |
| Rimbalzo del sensore del dispenser (C2) | Violazione di φ_count, intervallo sotto un secondo, nessuna variazione di contenuto | Sì |
| Replay di misure di pressione (C3) | Numeri di sequenza e timestamp; frequenza di polso incoerente con l'ECG corrente | Sì, con autenticazione; parziale senza |
| Evento di erogazione falsificato (C3) | Nessun testimone embodied; violazione di φ_resp dopo Δ2 | Parziale |
| Iniezione plausibile e coerente su tutti i canali da attaccante informato | Nessuna | **No, per costruzione** |

Questa tabella trasforma due affermazioni oggi non verificabili in limiti dichiarati: "a faulty sensor cannot masquerade as a clinical event" (smentito dalla quinta riga) e la rilevazione del tampering (limitata dall'ultima riga). I reviewer premiano i limiti dichiarati. Serve anche un **threat model** esplicito:
- **capacità dell'attaccante:** iniezione e replay BLE senza chiavi, accesso fisico al dispenser, spoofing della percezione;
- **esclusioni:** robot, RSM o specifica compromessi.

### 4.6 Coerenza temporale della Tabella I [MAGGIORE]

| Riga | Problema |
|---|---|
| 07:00 PILL, σ = +18, ρ = 0.97 | Non si dice di quale formula sia la robustness né in che unità. Il contatore (1 ≤ 2) avrebbe margine +1 dose. La finestra di risposta [08:00, 10:00] è aperta, quindi φ_resp è PENDING e il suo σ non è definito. Una "confidenza" su un evento soddisfatto non ha semantica. Inoltre un'apertura del dispenser non equivale all'assunzione. |
| 08:55 BP = 152, σ = −12, ρ = 0.94 | È l'unica riga coerente (140 − 152 = −12 mmHg). Però 08:55 non corrisponde a uno schedule dichiarato, e cade nella finestra di onset del farmaco: va chiarito clinicamente se il vincolo di range si applica durante l'onset. ρ = 0.94 sarebbe riproducibile con un modello d'errore del dispositivo (vedi §4.4). |
| 15:00 BP MEAS (9 s window), σ = −21, ρ = 0.71 | Unità implicita (secondi? 30 − 9 = 21?) mai dichiarata. Non è chiaro perché la confidenza sia bassa su un evento rilevato deterministicamente. La transizione a INACTIVE è un cambio di stato deliberato: un crash reale si rileva con liveliness o heartbeat, non con una transizione lifecycle. Le conseguenze non sono mostrate: la misura mancata fa fallire il contatore delle cinque misure a fine giornata, producendo un secondo alert "C1" con causa C2 (cascata non gestita). |
| 21:00 PILL, σ = +15, ρ = 0.96 | Stessi problemi della riga delle 07:00. |
| 21:02 PILL non programmato, σ = −8, ρ = 0.42, C3 | (a) Con il contatore a 3 su 2 la robustness è −1 dose, non −8. (b) §III-B dice che "the constraint checker fires on the cross-modal and dosage sub-formulae", ma le finestre di risposta per le erogazioni delle 21:00 e 21:02 si aprono alle 22:00 e 22:02: la sub-formula cross-modale **non può** essere violata alle 21:02, e "a PILL event without a downstream pressure decrease" non è osservabile prima delle 23:00 circa. (c) ρ basso su un predicato deterministico (vedi §4.4). (d) L'etichetta C3 è implausibile rispetto a un doppio prelievo o a un rimbalzo del sensore. (e) τ è indicato come singolo, ma il testo parla di due sub-formule violate. |

Nella versione RA-L questa tabella va eliminata e sostituita da una figura generata dal sistema reale su una traccia del benchmark (vedi §7).

### 4.7 Online monitoring con operatori futuri [MAGGIORE]

Il paper nomina il problema e non lo risolve. Gli strumenti standard sono tre, e vanno combinati.

1. **Riscrittura past-time**, come in §4.1. Ogni obbligo con finestra futura si valuta alla sua deadline con operatori once e historically. Il verdetto è causale, e la latenza massima del verdetto definitivo è limitata da Δ2 (o da W): va dichiarata come proprietà del monitor.
2. **Robustness interval su prefissi** (Deshmukh et al.). I valori futuri ignoti si sostituiscono con limiti fisiologici, per esempio pressione sistolica in [50, 250] mmHg, ottenendo [σ_lo, σ_hi]. Il verdetto è **VIOLATED** se σ_hi < 0, **SATISFIED** se σ_lo > 0, altrimenti **PENDING**. È una semantica a tre valori con robustness, sound per costruzione rispetto al modello di misura.
3. **Predictive completion nello stato PENDING.** I limiti fisiologici si sostituiscono con la regione di previsione conforme, ottenendo early warning con la garanzia di §4.4. Il verdetto definitivo arriva comunque dal passo 2 quando la finestra si chiude.

Nel paper servono un diagramma a stati (PENDING → PREDICTED-VIOLATION → VIOLATED oppure SATISFIED) e lo pseudocodice del ciclo di monitoring con la complessità per campione.

### 4.8 Claim non supportati: come renderli dimostrabili o ridimensionarli

| Claim attuale | Problema | Riformulazione proposta |
|---|---|---|
| "intrinsic explainability" (§II-B.d, §IV) | Puntare a una sub-formula è tracciabilità, non spiegazione della causa. Per C2 e C3 la causa è inferita da κ, quindi non è intrinseca. | "specification-level traceability: each alert references the violated template instance, its clinical parameters, and the evidence used for attribution". È dimostrabile con una resa in linguaggio naturale e, se possibile, con lo studio a vignette di §5.7. |
| "a faulty sensor cannot masquerade as a clinical event" (§III-A) | Falso per i guasti silenziosi (bias, stuck-at plausibile). | "faults that manifest in node health, device error codes, or signal quality are attributed to C2; silent faults producing plausible values remain indistinguishable from clinical deviations (Sec. X)", con il tasso misurato sul benchmark. |
| "two orthogonal axes" (§II-B.d) | σ e ρ sono correlati: vicino alla soglia ρ cala. | "complementary". |
| "natural taxonomy induced by the constraint structure" (§III-A) | C2 e C3 derivano dalle cause, non dalla struttura dei vincoli. | "a cause-based taxonomy over violations of φ_CP ∧ φ_SYS ∧ φ_INT". |
| "Embodiment as a safety asset… redundancy a passive network cannot" (§IV) | Non misurato; la ridondanza esiste solo quando il robot è presente. | Ablation con e senza canale embodied, riportando il guadagno su κ per C2 e C3 e dichiarando la copertura temporale. |
| "every alert goes through a single auditable verification path" (§II-A) | Letto da R3 come single point of failure. | Tenere l'auditabilità, aggiungere watchdog e fallback (vedi §4.9). |
| "distribution-free coverage" (§II-B.c) | Omette che la coverage è marginale e richiede exchangeability. | Esplicitarlo e indicare l'unità di calibrazione. |
| "beyond static edge-based solutions" (contributo 2) | Claim comparativo senza confronto. | Eliminare, oppure supportare con l'ablation. |
| "to assist nursing staff in real-world hospital wards" (abstract) | Nessun contesto reale. | Eliminare dall'abstract. |
| "ensures" (§III-A) | Linguaggio da garanzia senza prova. | "is designed to", salvo nei punti coperti dalla proposizione. |

### 4.9 Altri problemi

1. **[MAGGIORE] Architettura e portata BLE.** L'RSM sul robot come unico ricevitore degli stream è incompatibile con il monitoraggio continuo, con più pazienti e con i guasti del robot. Raccomando un'architettura distribuita:
   - un nodo di reparto fisso (gateway BLE più RSM per φ_CP continuo) monitora il robot con un heartbeat;
   - il robot esegue localmente il monitor delle specifiche embodied (task, deadline, testimone) e fornisce evidenza;
   - se il robot non è disponibile, il fallback escala all'infermiere.

   Il contributo robotico resta centrale, perché il robot esegue gli obblighi indotti dalla specifica ed è l'unico canale di testimonianza, e sparisce l'obiezione sul single point of failure.
2. **[MAGGIORE] Tempo.** Serve una semantica esplicita dei timestamp: tempo del dispositivo o di ricezione, sincronizzazione, buffer di riordino con ritardo massimo, e il suo effetto sulla latenza del verdetto. È anche un vettore di attacco (replay).
3. **[MAGGIORE] Violazioni a cascata e root cause.** Un C2 genera violazioni C1 a valle (misura mancata, contatore, risposta al farmaco non verificabile). L'attribuzione deve propagare la causa, altrimenti gli alert si moltiplicano.
4. **[MAGGIORE] Le safety action sono esse stesse hazard.** Bloccare il dispenser o interrompere una procedura può causare dosi mancate. Per le azioni cliniche serve un principio esplicito di clinician-in-the-loop, e un'autonomia limitata alle azioni del robot (fermarsi, ritentare, chiamare).
5. **[MAGGIORE] "PILL" confonde erogazione e assunzione.** L'apertura del dispenser non prova l'assunzione. È il punto debole di tutta l'aderenza, e distinguere DISPENSE da INTAKE (confermata dal robot) è un contributo embodied concreto.
6. **[MINORE] Fig. 1.**
   - La pipeline mostra Time-Series Learner → Constraint Checker → Conformal Uncertainty, ma il testo dice che la conformal "wraps the predictor".
   - Manca il blocco di signal abstraction.
   - Mancano gli ambient sensors, e soprattutto mancano gli esseri umani (infermiere, clinico, paziente).
   - "Safety Actions" non ha frecce in uscita.
   - La freccia "Patient data and Events" contraddice la "privacy-aware storage of feature representations".
   - §II-B.d parla di "three pipeline stages" contro i cinque blocchi della figura.
7. **[MINORE] Governance della specifica.** La "patient-specific calibration" dei parametri (§IV) va conciliata con "the robot only evaluates specifications it cannot author or modify": servono versioning e firma.
8. **[MINORE]** Il retrospective checking in cloud è descritto come esistente in §II-A e come lavoro futuro in §IV.

---

## 5. Piano sperimentale realistico

L'idea guida è una **validazione tecnica pre-clinica**:
- benchmark semi-sintetico con ground truth definita rigorosamente;
- integrazione ROS 2 in simulazione con misure di latenza;
- demo in laboratorio.

Nessun paziente reale, dichiarandolo apertamente.

### 5.1 Dati e costruzione delle tracce semi-sintetiche

**Fonti pubbliche.** Verificate schema, licenze e tempi di accesso.
- **MIMIC-IV** (Johnson et al., Scientific Data 2023). Il modulo hosp include la somministrazione dei farmaci (eMAR); il modulo ICU include misure intermittenti di pressione non invasiva. Il modulo **MIMIC-IV-ED** (†, verificate lo schema) dovrebbe contenere segni vitali periodici e dispensazioni da armadi automatici, un buon analogo del dispenser intelligente.
  - Uso principale: coppie reali farmaco antipertensivo → risposta pressoria, per stimare Δ1, Δ2, δ e la variabilità inter-paziente, e per calibrare il conformal.
  - Serve credentialing PhysioNet con corso CITI e data use agreement: **avviatelo subito**, può richiedere da alcuni giorni a qualche settimana.
- **eICU Collaborative Research Database** (Pollard et al., Scientific Data 2018). Stessi vincoli di accesso; tabelle con farmaci, vitali periodici e pressione aperiodica. È un secondo cohort utile per il test di distribution shift.
- **Accesso aperto:**
  - VitalDB (Lee et al., Scientific Data 2022), segnali intraoperatori ad alta risoluzione, utile per modellare rumore e artefatti;
  - BIDMC PPG and Respiration (†);
  - MIT-BIH Arrhythmia Database e **MIT-BIH Noise Stress Test Database**, con rumore reale da elettrodi e movimento, ideale per iniettare guasti C2 realistici su ECG;
  - PhysioNet/CinC Challenge 2015, falsi allarmi etichettati, utile come sanity check sul carico di allarmi.
- **Aderenza terapeutica:** non conosco dataset pubblici affidabili di dispenser intelligenti. Generate eventi con un modello a stati di aderenza (Markov con probabilità di ritardo, omissione e doppio prelievo), dichiarandolo come assunzione.

**Generatore di tracce.** È un contributo rilasciabile.
1. **Paziente latente:** pressione sistolica di base campionata da distribuzioni stimate sul cohort, componente circadiana con dip notturno, rumore autoregressivo, risposta al farmaco con modello PK/PD (assorbimento orale a un compartimento più effetto Emax) con parametri inter-paziente stimati da MIMIC.
   - In alternativa si può usare il Pulse Physiology Engine (open-source, Kitware), verificando che la sua libreria di sostanze includa antipertensivi adatti; in caso contrario resta il PK/PD custom.
2. **Processo di misura:** schedule del piano, jitter di arrivo del robot preso dalla simulazione (§5.2), errore del bracciale coerente con i criteri dei protocolli di validazione ISO 81060-2 (verificate i valori), frequenza cardiaca e SpO₂ da segmenti reali.
3. **Iniezione controllata, con onset, durata e magnitudo parametrizzati:**
   - **C1:** picchi ipertensivi, non-risposta (Emax ridotto), ipotensione sotto l'hold parameter, rifiuto della misura.
   - **C2:** dropout BLE con transizione del nodo; stuck-at; bias silenzioso del bracciale (per misurare onestamente il limite); rumore NSTDB sull'ECG; ritardo di navigazione; fallimento di manipolazione; rimbalzo del sensore del dispenser.
   - **C3:** replay di misure dal giorno precedente, iniezione di valori plausibili a due livelli di conoscenza dell'attaccante (ingenuo e informato), erogazione falsificata, presenza simulata.
4. **Confondenti deliberati:** non-risposta reale contro erogazione falsificata, doppio prelievo contro rimbalzo del sensore. Sono i casi in cui κ deve astenersi o usare il testimone.

**Ground truth, da definire con precisione.** Una violazione C1 vera è una violazione di φ_CP sulla traccia **latente** (senza rumore, guasti o attacchi). C2 e C3 veri sono gli eventi iniettati. Il monitor vede solo le osservazioni corrotte. Questo rende la valutazione non tautologica, e va spiegato perché è la prima obiezione di R2 (vedi §10).

**Scala indicativa:** 200 pazienti virtuali × 7 giorni = 1400 giorni-paziente, con split per paziente (training del predittore, calibrazione, test), almeno 5 seed, intervalli di confidenza bootstrap. Aggiungete un **run su dati reali non etichettati** (episodi MIMIC-IV-ED o eICU senza iniezione) per riportare il carico di alert per giorno-paziente su dati veri.

### 5.2 Setup in simulazione

- **ROS 2** (Humble o Jazzy, a seconda dei pacchetti TIAGo disponibili) con **Gazebo**, Nav2 e un ambiente ospedaliero. Esiste un "hospital world" AWS RoboMaker per Gazebo (verificate il supporto ROS 2 e l'eventuale porting dal Gazebo classic). Per gli umani in movimento potete valutare HuNavSim (†). Isaac Sim è opzionale e costoso in GPU: per un gruppo piccolo sconsiglio.
- **Verificate i pacchetti di simulazione PAL**, in particolare se esiste un modello TIAGo Pro per ROS 2 o solo TIAGo.
- **Dispositivi simulati** come lifecycle node ROS 2 che riproducono le tracce del benchmark e usano il profilo BLE standard per la pressione come modello dei messaggi. Guasti iniettati con transizioni lifecycle, kill del processo, drop dei messaggi (per esempio tc netem), rumore sulla localizzazione e goal di navigazione impossibili.
- **Scenario:** un robot, 4–8 stanze, piani di cura sfalsati. Il robot deve rispettare gli obblighi di misura indotti da φ_resp e φ_sched. È lo scenario naturale per il predictive monitoring delle deadline (§4.3).
- **Misure:** latenza end-to-end dal campione all'alert con ros2_tracing (p50, p95, p99), CPU e memoria su hardware equivalente a quello di bordo (verificate le specifiche del computer del TIAGo), throughput con N pazienti × M template in parallelo.

### 5.3 Robot reale in laboratorio

Fortemente raccomandato per RA-L, non strettamente indispensabile.
- Laboratorio che simula una stanza di reparto, con letto e manichino o volontario sano.
- Dispositivi emulati su schede BLE programmabili per avere eventi controllabili, più un dispositivo commerciale reale per realismo.
- Dispenser costruito con microcontrollore, serratura, sensore di apertura e cella di carico, con caramelle placebo.
- Timeline compressa con fattore dichiarato, per esempio 1 ora = 2 minuti.
- 3–5 scenari scriptati per classe, circa 10 ripetizioni ciascuno.
- Misure: latenza, correttezza dell'attribuzione, successo dei task, conferma dell'assunzione via percezione.
- Con volontari umani, anche sani e con dispositivi non invasivi, verificate le regole del vostro comitato etico. Il manichino con segnali emulati evita il problema.

### 5.4 Baseline

| Baseline | Descrizione | Cosa mostra |
|---|---|---|
| B1 Soglie statiche | Stesse bande del piano, allarme su ogni campione fuori banda, più logica di schedule semplice | Il valore di struttura temporale, finestre e attribuzione a parità di conoscenza clinica |
| B2 Anomaly detection | Residuo di forecasting (z-score) e/o Isolation Forest su feature | Il confronto con l'approccio da cui il paper si distingue |
| B3 STL senza incertezza | Stessi template con RTAMT, verdetti sui valori misurati, robustness grezza non normalizzata | Il contributo di conformal e normalizzazione |
| B4 Conformal senza STL | Allarme quando la misura esce dall'intervallo conforme di previsione (conformal anomaly detection) | Il contributo della specifica |
| B5 Conformal STL predictive monitoring, alla Lindemann et al. 2023 | Il metodo pubblicato più vicino, applicato ai vostri template | **Indispensabile** per difendere la novità: mostrate dove fallisce (campionamento sparso, unità miste, nessuna attribuzione) |

### 5.5 Metriche

- **Rilevamento per classe:** precision, recall e F1 a livello di evento, con finestra di tolleranza per il matching dichiarata.
- **Tempo di rilevamento** rispetto al primo istante decidibile: per vincoli con finestra, rispetto alla deadline Δ2. Valori negativi indicano early warning; riportate la distribuzione dell'anticipo.
- **Falsi allarmi per giorno-paziente**, e curve di recall contro falsi allarmi al variare di α.
- **Coverage empirica** contro nominale su una griglia di α, e ampiezza media degli intervalli, sia in distribuzione sia sotto shift (calibrazione su un cohort, test sull'altro).
- **Calibrazione di ρ:** reliability diagram ed expected calibration error per le violazioni predette.
- **Attribuzione κ:** matrice di confusione inclusa UNDETERMINED, macro-F1, tasso di astensione, curva accuratezza contro copertura.
- **Sistema:** latenza p50, p95 e p99, CPU %, memoria, scalabilità con il numero di pazienti.
- **Opzionale:** accordo tra ordinamento per severità normalizzata e ordinamento dato da clinici (Kendall o Spearman).

### 5.6 Ablation

| Ablation | Componente rimosso | Ipotesi da verificare |
|---|---|---|
| A1 | Conformal, sostituita da previsione puntuale | Più falsi allarmi predittivi e ρ non calibrato |
| A2 | Predittore (solo verdetti misurati a tre valori) | Nessun early warning; stessi verdetti definitivi |
| A3 | Normalizzazione di σ | Peggiore accordo nell'ordinamento degli alert |
| A4 | Canale embodied (lifecycle robot, percezione, testimone) | Crollo di κ su C2 robotici e su erogazioni falsificate |
| A5 | Vincoli cross-modali e hold parameter | Recall ridotta su non-risposta e ipotensione |
| A6 | Split conformal contro adaptive conformal sotto shift | Degrado della coverage e recupero parziale con la variante adattiva |
| A7 | Formulazione past-time contro future con ritardo | Equivalenza dei verdetti, differenze di latenza e implementazione |

A4 è l'ablation strategicamente più importante: è la risposta quantitativa a "perché serve un robot?".

### 5.7 Valutazione qualitativa con clinici (opzionale ma preziosa per R3)

- **Formato:** studio a vignette con 8–15 infermieri o medici di un ospedale partner, online e within-subject.
- **Condizioni:** lo stesso evento presentato come allarme da soglia, come anomaly score e come alert RSM reso in linguaggio naturale (template violato, severità, confidenza, causa attribuita).
- **Misure:**
  - correttezza dell'azione scelta rispetto a una chiave definita da un esperto;
  - tempo di decisione;
  - interpretabilità percepita (Likert);
  - fiducia, con una scala validata come quella di Jian et al. (†, International Journal of Cognitive Ergonomics 2000);
  - comportamento quando severità e confidenza divergono, domanda già posta in §IV del paper.
- Verificate se serve approvazione etica o se basta un'esenzione.

### 5.8 Cosa è indispensabile e cosa è opzionale

| Elemento | Stato |
|---|---|
| Formalizzazione completa (template, normalizzazione, ρ, verdetti a tre valori, proposizione) | **Indispensabile** |
| Threat model, fault model e matrice di diagnosabilità | **Indispensabile** |
| Benchmark semi-sintetico con ground truth latente e parametri stimati da dati reali | **Indispensabile** |
| Baseline B1–B5, con B5 obbligatoria | **Indispensabile** |
| Ablation A1–A4 | **Indispensabile** |
| Integrazione ROS 2 in simulazione con TIAGo, guasti robotici e latenza | **Indispensabile** per il fit con RA-L |
| Run su dati reali non etichettati per il carico di allarmi | Fortemente raccomandato, costo basso |
| Demo su robot reale in laboratorio | Fortemente raccomandato |
| Test sotto distribution shift (A6) | Raccomandato |
| Seconda patologia, per esempio diabete con simulatore UVA/Padova open-source (simglucose) | Opzionale, forte segnale di generalità |
| Studio a vignette con clinici | Opzionale, alto valore per R3 |
| Isaac Sim, variante probabilistica di κ | Opzionali |

---

## 6. Contributi rivisti

Da adattare ai risultati reali. I placeholder tra parentesi quadre vanno riempiti o eliminati.

- **Pathway-grounded specification.** We introduce a library of [K] parametric past-time Signal Temporal Logic templates that encode care-plan constraints (physiological ranges, measurement schedules, action ordering, dose counts, and dose–response windows) over sparsely and irregularly sampled clinical signals, together with a clinically normalized robustness that makes severity comparable across heterogeneous units. The templates cover [M] of [M′] constraints of [two] clinician-reviewed care pathways.
- **Uncertainty-aware three-valued monitoring.** We define an online monitor that issues definitive verdicts from measured data via robustness intervals and, while obligations are pending, predictive warnings whose false-alarm probability is bounded by α under exchangeability through conformal calibration (Proposition 1), with an adaptive variant evaluated under distribution shift.
- **Evidence-based attribution with embodied witnessing.** We propose an attribution layer that labels each alert as a clinical deviation, a system or embodiment failure, or an integrity violation, or abstains, by combining sub-formula provenance, ROS 2 node health, cross-device consistency, and on-robot perception under an explicit fault and threat model. We characterize which event types are distinguishable with which evidence channels.
- **Implementation and evaluation.** We release an open-source ROS 2 implementation and a semi-synthetic benchmark of [N] patient-days derived from public clinical data with [E] injected events. We compare against threshold, anomaly-detection, plain-STL, conformal-only, and conformal-STL baselines in simulation and in a mock-ward deployment on a TIAGo robot, reporting per-class precision and recall, detection delay, false alarms per patient-day, empirical coverage, attribution accuracy, and on-board latency.

---

## 7. Struttura proposta per le 6 pagine

Verificate nel CFP se i riferimenti rientrano nelle 6 pagine e quale sia la politica sulle pagine extra. Pianifico nello scenario peggiore, cioè riferimenti inclusi.

| Sezione | Contenuto | Spazio | Figure e tabelle |
|---|---|---|---|
| I. Introduction | Problema, gap (anomaly score contro specifica, "why embodiment"), 4 contributi, frase esplicita sulla differenza rispetto al workshop paper | 0.6 p | Fig. 1 (colonna singola) |
| II. Related Work | Quattro paragrafi densi: STL runtime monitoring e RV in robotica; conformal e predictive monitoring; guideline formalization e medical CPS; robot in sanità e sicurezza dei dispositivi. Ognuno chiuso da una frase sulla differenza | 0.45 p | — |
| III. Problem Formulation | Segnali e campionamento; care plan contro template di pathway; φ = φ_CP ∧ φ_SYS ∧ φ_INT; fault e threat model; definizione della tupla di alert | 0.5 p | — |
| IV-A. Specification templates | Template, segnali derivati, time robustness | 0.5 p | Tabella I: template, formula, unità, scala s_π, priorità |
| IV-B. Severity and confidence | Normalizzazione, ordinamento lessicografico, definizioni di ρ | 0.3 p | — |
| IV-C. Three-valued predictive monitoring | Robustness interval, completion conforme, Proposition 1 con dimostrazione in 3–4 righe, algoritmo compatto | 0.45 p | Algoritmo in 10 righe (opzionale) |
| IV-D. Attribution | Evidenze, regola con astensione, matrice di diagnosabilità compatta | 0.3 p | Può confluire nella Tabella III |
| IV-E. ROS 2 realization | Nodi, placement distribuito (nodo di reparto più robot), watchdog e fallback | 0.15 p | Integrata in Fig. 1 |
| V-A/B. Setup | Benchmark, iniezione, ground truth latente, baseline, metriche, simulazione, laboratorio | 0.5 p | — |
| V-C. Results | Rilevamento per classe, falsi allarmi per giorno-paziente, ritardi, coverage | 0.6 p | Tabella II risultati principali; Fig. 2 traccia di un giorno-paziente |
| V-D. Ablations and shift | A1–A6 e shift | 0.35 p | Fig. 3 (due pannelli: recall contro falsi allarmi; coverage contro α) oppure Tabella III |
| V-E. Robot deployment | Latenza, attribuzione in laboratorio | 0.25 p | Fig. 4 piccola: foto più grafico ROS (opzionale) |
| VI. Discussion and Limitations | Guasti silenziosi, attaccante informato, dati semi-sintetici, validazione clinica | 0.3 p | — |
| VII. Conclusion | Tre righe | 0.1 p | — |
| References | 30–35 voci | 0.6 p | — |

**Figure chiave.**
- **Fig. 1:** architettura ridisegnata con pipeline corretta (signal abstraction → monitor misurato e predittivo → attribuzione → event manager → umani e robot), umani esplicitamente presenti, distinzione tra componenti sul percorso critico e fuori.
- **Fig. 2:** una giornata-paziente dal benchmark, con robustness normalizzata per template nel tempo, misure puntuali, banda conforme predetta, stati PENDING, PREDICTED e VIOLATED, eventi iniettati evidenziati. Sostituisce la Tabella I e mostra visivamente la semantica.
- **Tabella II:** righe per metodo (B1–B5 e il vostro), colonne per F1 C1, C2, C3, falsi allarmi per giorno-paziente, ritardo mediano, coverage.

**Cosa tagliare o comprimere dal testo attuale.**
1. §II-A, descrizione narrativa dei sottosistemi e del dataflow pull/push: da circa 0.6 a 0.15 pagine, più la figura.
2. §II-B.b, spiegazione tutorial di □ e ♢: eliminare e sostituire con definizioni formali. R1 non ne ha bisogno, gli altri reviewer la trovano in Related Work.
3. Tabella I e §III-B: la tabella va eliminata. Lo scenario ipertensione resta in 3–4 righe come patologia del benchmark in V-A.
4. §III-A, prosa della tassonomia: confluisce in definizioni brevi in III.
5. §IV, paragrafo "Three aspects connect this work to the trustworthy-AI agenda": eliminare, è retorica.
6. §IV, lavoro futuro: eliminare ciò che diventa contributo, tenere i limiti reali in VI.
7. Conclusione: da un paragrafo a tre righe.
8. Frasi ripetute: "whether prescribed care is delivered safely" compare almeno quattro volte, e la contrapposizione anomaly detection contro specification-based compare in introduzione, §IV e conclusione. Tenerla una volta sola, in introduzione.

---

## 8. Qualità della scrittura

### 8.1 Terminologia incoerente

| Termine attuale | Problema | Proposta |
|---|---|---|
| "edge cloud subsystem" (testo), "CLOUD SUBSYSTEM" (Fig. 1), "keeps safety reasoning at the edge" | Non è chiaro se l'edge sia il robot o il cloud | "back-end (off the safety-critical path)" oppure "ward server"; definire una volta on-path contro off-path |
| "subsystem" per sensing, embodied e cloud, ma anche per signal abstraction, uncertainty e temporal prediction | Granularità diverse con lo stesso nome | "tier" per i livelli architetturali; "module" per i componenti dell'RSM; "node" per i processi ROS 2 |
| "multivariate time-series learner" / "temporal prediction subsystem" / "Time-Series Learner" | Tre nomi per lo stesso componente | "forecaster" |
| "calibrated uncertainty subsystem" / "uncertainty subsystem" / "conformal subsystem" / "Conformal Uncertainty" | Quattro nomi | "conformal calibrator" |
| "Clinical Pathway" per la prescrizione del singolo paziente | Uso improprio in senso clinico | "pathway template" istanziato in un "patient care plan" |
| "Physical AI", "embodied medical AI", "embodied AI", "clinical robotic architecture" | Sinonimi non dichiarati | "Physical AI" solo nel titolo e nel framing; poi "assistive robot" e "monitoring architecture" |
| "robust" semantics contro "robust evaluation under noise" | Due sensi diversi | Riservare "robustness" alla semantica STL |
| "PILL" / "dispenser open" / "intake" | Erogazione e assunzione confuse | DISPENSE contro INTAKE (verified) |
| "violation" usato per C2 e C3 | Un guasto non è una violazione del piano di cura | "alert" per l'output, "violation" per la sub-formula, "attributed cause" per κ |
| "smart medical devices" / "smart-medical devices" | Refuso | Uniformare |

### 8.2 Altri problemi di chiarezza

- **Abstract:** 180 parole senza nessun elemento verificabile. "combines temporal prediction, uncertainty-aware reasoning, and constraint-based verification" è vago e sovrapposto alla letteratura esistente. Non compaiono né STL né conformal prediction. Chiude con un claim di impatto reale non supportato.
- **Tassonomia:** "natural", "practical pay-off", "conceptual core" (usato due volte per cose diverse, §II-A e §II-B.a) sono enfasi senza contenuto.
- **Gergo e riferimenti mancanti:** "missed deadlines on safety-critical topics" è gergo ROS non spiegato; φ_HW e φ_DOSE sono introdotti solo nella caption.
- **Frasi da riformulare in forma operativa:** "Their operational states are observable to the RSM and used to disambiguate sensor faults from clinical events" va sostituita con il meccanismo concreto.
- **Index Terms:** RA-L richiede keyword da una lista controllata. Candidati da verificare: Robot Safety; Formal Methods in Robotics and Automation; Medical Robots and Systems; Human-Centered Robotics.

### 8.3 Titoli proposti

1. **"Clinical Pathways as Runtime Safety Specifications: Uncertainty-Aware Monitoring for Assistive Robots in Hospital Wards"**. Mantiene la continuità con il workshop e aggiunge metodo e piattaforma.
2. **"Monitoring Prescribed Care at Runtime: Conformal Signal Temporal Logic for Assistive Robots in Hospital Wards"**. Il più tecnico, e dichiara subito il metodo a R1 e R2.
3. **"Pathway-Grounded Runtime Safety Monitoring for Physical AI in Hospital Wards"**. Il più breve, allineato al titolo della special issue, ma meno informativo sul metodo.

Raccomando il primo.

### 8.4 Abstract proposto (182 parole)

> Assistive robots and wearable devices are entering hospital wards, but their runtime safety is usually monitored with anomaly scores that neither refer to the prescribed care nor separate patient deterioration from device faults or data manipulation. We treat Clinical Pathways, instantiated into patient-specific care plans, as runtime safety specifications. Range, schedule, ordering, dose-count, and dose–response constraints are encoded as past-time Signal Temporal Logic templates with clinically normalized robustness, making alerts comparable across heterogeneous units. A monitor running as ROS 2 nodes on a mobile manipulator distinguishes violations observed in measured data from predicted violations, whose confidence is calibrated by conformal prediction. An attribution layer fuses violated sub-formulas, node health, and on-robot perception to label each alert as a clinical deviation, a system failure, or an integrity violation, or as undetermined. We evaluate on [N] semi-synthetic patient-days derived from MIMIC-IV with injected events, against threshold, anomaly-detection, plain-STL, and conformal-only baselines, and in a mock-ward deployment on a TIAGo robot. The monitor reaches [X] recall at [Y] false alarms per patient-day, with empirical coverage within [Z] points of nominal and [W] ms on-board latency.

**Variante per la commitment letter**, quando i numeri non ci sono ancora: sostituire l'ultima frase con "We report per-class detection, false alarms per patient-day, empirical coverage, and on-board latency." Verificate anche che dataset e robot citati corrispondano a ciò che userete davvero.

---

## 9. Roadmap prioritaria

Lo sforzo è espresso in person-week (pw).

### Fase 0: commitment letter (entro 1–2 settimane)

| # | Azione | Impatto | Sforzo | Dipendenze |
|---|---|---|---|---|
| 0.1 | Verificare il CFP: scadenze, limite di pagine (riferimenti inclusi o no), politica sulla pubblicazione precedente di workshop paper (l'archivialità degli atti del workshop IJCAI-ECAI va verificata), contenuto richiesto della commitment letter e possibilità di modificare autori e titolo in seguito | Alto (evita desk reject) | 0.5 giorni | — |
| 0.2 | Decisioni di scope: una patologia principale; C3 ridimensionato a "integrity violations" con threat model; architettura distribuita (nodo di reparto più robot) | Alto | 2–3 giorni | 0.1 |
| 0.3 | Autori: coinvolgere un clinico (internista, cardiologo o coordinatore infermieristico) per parametri, tassonomia e vignette, e se possibile un collaboratore con esperienza in RV o STL | Alto (R3 e R1) | Contatti | 0.2 |
| 0.4 | Titolo (§8.3) | Medio | 1 ora | 0.2 |
| 0.5 | Abstract senza numeri (§8.4) | Medio | 2 ore | 0.2 |
| 0.6 | Avviare il credentialing PhysioNet per MIMIC-IV ed eICU | Alto (percorso critico) | 1 giorno più attesa | — |
| 0.7 | Verificare disponibilità del TIAGo o TIAGo Pro reale e dei pacchetti di simulazione ROS 2 | Medio | 1 giorno | — |

### Fasi successive: submission completa (circa 14–16 settimane, lavoro in parallelo)

| # | Azione | Impatto | Sforzo | Dipendenze |
|---|---|---|---|---|
| 1 | Problem formulation, template STL, normalizzazione, definizioni di ρ, semantica a tre valori, Proposition 1 | Alto | 3–4 pw | 0.2 |
| 2 | Threat model, fault model, matrice di diagnosabilità, regola di attribuzione con astensione | Alto | 1–2 pw | 1 |
| 3 | Related work con verifica di tutti i riferimenti (§3) | Alto | 1.5 pw | Parallelo |
| 4 | Generatore di benchmark (PK/PD, processo di misura, iniezione, confondenti, ground truth latente) con parametri stimati da dati reali | Alto | 4–6 pw | 0.6, 1 |
| 5 | Implementazione del monitor come nodi ROS 2 (RTAMT o custom), calibratore conforme, attribuzione | Alto | 4–5 pw | 1, 2 |
| 6 | Baseline B1–B5 | Alto | 2–3 pw | 4 |
| 7 | Simulazione ROS 2 e Gazebo con TIAGo, guasti robotici, latenza, predictive monitoring delle deadline | Alto (fit con RA-L) | 3–4 pw | 5 |
| 8 | Esperimenti principali, ablation A1–A6, test di shift, run su dati reali non etichettati | Alto | 3 pw | 4, 5, 6 |
| 9 | Figure 1–3 e Tabelle I–III | Medio | 1.5 pw | 8 |
| 10 | Demo su robot reale in laboratorio | Medio-alto | 3 pw | 7 |
| 11 | Studio a vignette con clinici | Medio | 3 pw più tempi etici | 5, 0.3 |
| 12 | Scrittura, review interna in ruolo "avvocato del diavolo" con questa analisi come checklist | Alto | 2–3 pw | Tutte |
| 13 | Repository open-source anonimizzabile e documentato | Medio | 1 pw | 5, 4 |

Il totale è di circa 33–42 pw, fattibile per 3–4 persone in 3–4 mesi se 4, 5 e 7 procedono in parallelo. Se il tempo stringe, tagliate nell'ordine 11, poi 10 (sostituendolo con un video in simulazione, sapendo che indebolisce il fit), poi la seconda patologia. **Non tagliate** B5, A4 né la formalizzazione.

---

## 10. Rischi residui: le tre obiezioni più probabili anche nella versione migliorata

### 1. "La valutazione è semi-sintetica e circolare: vince chi ha scritto la specifica usata per generare la ground truth."

**Prevenzione nel testo:**
- definire la ground truth sulla traccia latente, mentre il monitor osserva dati con rumore, guasti e attacchi;
- dare alle baseline la stessa conoscenza clinica (bande e schedule per B1 e B3);
- riportare il carico di alert su dati reali non etichettati;
- stimare i parametri da MIMIC e farli rivedere a un clinico;
- dichiarare nell'abstract, nell'introduzione e nei limiti che si tratta di validazione tecnica pre-clinica;
- rilasciare il generatore, così la circolarità è ispezionabile.

### 2. "È un'applicazione incrementale del conformal STL runtime verification a un dominio clinico."

**Prevenzione nel testo:**
- citare esplicitamente Lindemann et al. 2023 e il filone di Bortolussi e Cairoli in Related Work, con una frase di differenza precisa: campionamento sparso ed event-driven, separazione formale tra verdetto misurato e predetto, severità normalizzata su unità miste, attribuzione con astensione;
- includere quel metodo come baseline B5 e mostrare almeno un risultato in cui fallisce;
- presentare la Proposition 1 come piccola ma nuova nel setting a tre valori, senza gonfiarla.

### 3. "Il robot non è necessario: è un host del monitor, e introduce più rischi di quanti ne mitighi."

**Prevenzione nel testo:**
- rendere il robot parte della specifica: gli obblighi di misura e di testimonianza indotti da φ_resp e φ_INT sono task del robot, monitorati e predetti;
- riportare l'ablation A4 con numeri;
- aggiungere il predictive monitoring delle deadline di care delivery;
- misurare la latenza a bordo e portare la demo in laboratorio;
- dedicare un paragrafo a hazard, riferimenti normativi e fallback quando il robot non è disponibile;
- nell'introduzione, chiudere il gap con una frase che risponde direttamente a "why embodiment".

La quarta obiezione più probabile riguarda C3 ("un attaccante informato è invisibile"). Si previene riportando nella matrice di diagnosabilità i casi non rilevabili come risultato, non come nota a margine.
