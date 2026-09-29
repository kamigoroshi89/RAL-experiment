# Rilievi dei reviewer (estratto verbatim di analisi.md §2)

*Estratto meccanico delle righe 32-153 di `analisi_RAL_clinical_pathways.md`, sezione "Simulazione di review RA-L" (R1, R2, R3, meta-review AE). Nessuna modifica al testo. Vedi ADR-012 in `docs/plan/03-decisions.md`.*

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
