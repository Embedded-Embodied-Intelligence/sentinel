# Sentinel v3: rejestr dowodów, przegląd rynku, grupy do ankiety i projekt badania „Human in the Loop”

Najmocniej udokumentowana odpowiedź na pytanie promotora brzmi: LLM w firmie ma sens tam, gdzie wykonuje pracę językową, a jego wynik człowiek lub kod mogą tanio sprawdzić (redakcja raportów, streszczenia, tłumaczenie danych na tekst i odwrotnie). Ryzyko pojawia się tam, gdzie LLM liczy, decyduje o pieniądzach lub ocenia ludzi. Dlatego granica w Sentinelu nie powinna przebiegać według kryterium „AI tylko do oszczędzania czasu”, lecz według weryfikowalności, odwracalności i wpływu na ludzi.

## TL;DR
- **Moduły „AI tak, z człowiekiem” (Raporty, Projekty, Finanse) mają mocne oparcie w badaniach.** W pracy tekstowej LLM daje −40% czasu i +18% jakości (eksperyment w Science, 453 profesjonalistów), ale w zadaniu „poza granicą” możliwości modelu trafność spada o 19 punktów procentowych. W benchmarku finansowym GPT-4-Turbo z wyszukiwaniem odpowiedział błędnie lub odmówił w 81% pytań. To uzasadnia zasadę Sentinela: liczby z kodu i symulacji, LLM tylko je tłumaczy.
- **Najważniejsze kontrdowody trzeba pokazać wprost.** Wyjaśnienia AI zwiększają akceptację rekomendacji niezależnie od ich poprawności (Bansal i in., CHI 2021), a „człowiek w pętli” podlega automation bias, co AI Act nazywa wprost w art. 14(4)(b). Moduł Projekty powinien mieć „cognitive forcing” (najpierw własna ocena, potem rekomendacja), co według Buçinki i in. zmniejsza nadmierne poleganie na AI, choć użytkownicy oceniają to gorzej.
- **Twierdzenie „takich narzędzi jeszcze nie ma” wymaga zniuansowania.** W listopadzie 2026 istnieją Microsoft 365 Copilot z funkcjami księgowymi i Atlassian Rovo z agentami, uprawnieniami i logami audytu. Human-in-the-loop jest w nich jednak opcją konfiguracji (w Rovo zatwierdzanie w czacie, ale nie w automatyzacjach; logi wywołań agentów w droższym planie). Nie mają „mapy granic” z uzasadnieniem naukowym ani funkcji celowo nieistniejących, i na tym polega oryginalność Sentinela.

## Kluczowe wnioski (do slajdu otwierającego)
1. **Kryterium „oszczędność czasu” jest za słabe.** Raisch i Krakowski (2021) pokazują, że w zarządzaniu automatyzacji nie da się czysto oddzielić od augmentacji.\[1\] Lepsza oś: weryfikowalność × odwracalność × wpływ na ludzi.
2. **Granica „smaku” (judgment) jest empirycznie najsłabiej udowodniona.** Źródła są tu głównie teoretyczne (Polanyi/Autor, Agrawal i in.); warto to uczciwie przyznać na obronie.
3. **Moduł Ludzie („celowo NIE”) ma najmocniejsze oparcie prawne:** Załącznik III pkt 4(b) AI Act\[2\] i zakaz rozpoznawania emocji w pracy (od 2 lutego 2025).\[3\] Rozporządzenie (UE) 2026/1744 („Digital Omnibus”) przesunęło obowiązki dla systemów wysokiego ryzyka z Załącznika III na 2 grudnia 2027 r. i złagodziło art. 4,\[4\]\[5\] ale klasyfikacja jako wysokie ryzyko pozostała.\[6\]
4. **Moduł Uprawnienia AI odpowiada wprost na trzy przyczyny „Excessive Agency” według OWASP** (nadmierna funkcjonalność, uprawnienia, autonomia).\[7\] „LLM bez narzędzi, tylko JSON ze schematem” usuwa wszystkie trzy.

---

## A. Rejestr dowodów (Evidence registry)

**Format rekordu:** id · moduł/kryterium · decyzja · stanowisko (WSPIERA / PODWAŻA / NIUANSUJE) · cytat (EN) + glosa PL · miejsce · źródło · DOI/URL · open access · streszczenie.
**Weryfikacja:** „✔” = cytat sprawdzony w tekście źródła (abstrakt lub pełny tekst) w tym badaniu; „✖ cytat niezweryfikowany” = tylko streszczenie, cytat trzeba przepisać z PDF przed użyciem w pop-upie.

### Moduł 1 — Raporty („AI tak, z człowiekiem”)

**E01** · M1 · Kryt. 3 (praca językowa) · AI redaguje tekst napisany przez człowieka · **WSPIERA** · ✔
- Cytat: "Our results show that ChatGPT substantially raised productivity: The average time taken decreased by 40% and output quality rose by 18%." Glosa: ChatGPT skrócił czas pisania o 40% i podniósł jakość o 18%.\[8\]
- Cytat 2: "Inequality between workers decreased, and concern and excitement about AI temporarily rose." Glosa: różnice między pracownikami zmalały.\[9\]
- Miejsce: Abstract.
- Źródło: Noy, S., Zhang, W. (2023). Experimental evidence on the productivity effects of generative artificial intelligence. *Science*, 381(6654), 187–192.\[10\]
- DOI: 10.1126/science.adh2586 · OA: Science płatny; wersja robocza otwarta (SSRN 4375283, MIT Economics).\[9\]\[11\]
- Streszczenie: Prerejestrowany eksperyment online: 453 profesjonalistów z wyższym wykształceniem wykonywało zawodowe zadania pisarskie, połowa losowo z ChatGPT. Czas spadł o 40%, jakość oceniana przez ekspertów wzrosła o 18%, najsłabsi zyskali najwięcej.\[8\]\[9\] Uwaga: zadania były krótkie (~20–30 min) i nie wymagały weryfikacji faktów.

**E02** · M1, M3, M6 · Kryt. 3 · AI tylko „wewnątrz granicy”; liczby i nowe osądy poza nią · **WSPIERA (granicę) / PODWAŻA (bezwarunkowe użycie)** · ✔
- Cytat: "We suggest that the capabilities of AI create a “jagged technological frontier” where some tasks are easily done by AI, while others, though seemingly similar in difficulty level, are outside the current capability of AI." Glosa: możliwości AI tworzą „postrzępioną granicę”; zadania pozornie podobne leżą po różnych stronach.\[12\]
- Cytat 2: "For a task selected to be outside the frontier, however, consultants using AI were 19 percentage points less likely to produce correct solutions compared to those without AI." Glosa: poza granicą konsultanci z AI mieli o 19 pp. mniej poprawnych rozwiązań.\[12\]
- Cytat 3: "Within this growing frontier, AI can complement or even displace human work; outside of the frontier, AI output is inaccurate, less useful, and degrades human performance." Glosa: poza granicą AI obniża wyniki człowieka.\[12\]
- Miejsce: Abstract (s. 2); Introduction (s. 1 numeracji WP).
- Źródło: Dell'Acqua, F., McFowland III, E., Mollick, E., Lifshitz-Assaf, H., Kellogg, K.C., Rajendran, S., Krayer, L., Candelon, F., Lakhani, K.R. (2023). Navigating the Jagged Technological Frontier… HBS Working Paper 24-013.\[12\] Według późniejszych cytowań: *Organization Science* 37(2), 2026, DOI 10.1287/orsc.2025.21838 (niezweryfikowane; cytuj WP).\[13\]
- URL: https://mitsloan.mit.edu/sites/default/files/2023-10/SSRN-id4573321.pdf · OA: tak.
- Streszczenie: Prerejestrowany eksperyment z 758 konsultantami BCG (~7% konsultantów indywidualnych): bez AI, GPT-4, GPT-4 + szkolenie. W 18 zadaniach „wewnątrz granicy”: +12,2% zadań, 25,1% szybciej, ponad 40% lepsza jakość. W zadaniu „poza granicą” (analiza danych i wywiadów) trafność spadła o 19 pp.; autorzy opisują wzorce „Centaurów” i „Cyborgów”.\[12\]

**E03** · M1 · Kryt. 2 · Kod sprawdza, że liczby, daty i nazwy przetrwały redakcję · **WSPIERA** · ✔
- Cytat: "it is also apparent that deep learning based generation is prone to hallucinate unintended text, which degrades the system performance and fails to meet user expectations in many real-world scenarios." Glosa: generacja tekstu ma skłonność do „halucynowania” niezamierzonych treści.\[14\]
- Miejsce: Abstract.
- Źródło: Ji, Z., Lee, N., Frieske, R., Yu, T., Su, D., Xu, Y., Ishii, E., Bang, Y., Madotto, A., Fung, P. (2023). Survey of Hallucination in Natural Language Generation. *ACM Computing Surveys*, 55(12).\[14\]
- DOI: 10.1145/3571730 · arXiv: 2202.03629 · OA: tak (CC BY 4.0).\[14\]
- Streszczenie: Przegląd metryk i metod ograniczania halucynacji w streszczaniu, dialogu, QA, data-to-text i tłumaczeniu, z częścią o LLM.\[14\] Streszczenie abstrakcyjne jest jednym z głównych miejsc niezgodności z tekstem źródłowym, co uzasadnia deterministyczny „strażnik” encji i liczb.

**E04** · M1, M2 · Kryt. 1, 2 · Tracked changes: człowiek przyjmuje lub odrzuca każdą zmianę · **WSPIERA** · ✔ (preprint)
- Cytat: "In incentivized forecasting tasks, we find that people are considerably more likely to choose to use an algorithm, and thus perform better, when they can modify its forecasts. Importantly, this is true even when they are severely restricted in the modifications they can make." Glosa: ludzie chętniej używają algorytmu, gdy mogą choć trochę modyfikować wynik.\[15\]
- Miejsce: Abstract preprintu; brzmienie wersji opublikowanej sprawdź w PDF Management Science.
- Źródło: Dietvorst, B.J., Simmons, J.P., Massey, C. (2018). Overcoming Algorithm Aversion: People Will Use Imperfect Algorithms If They Can (Even Slightly) Modify Them. *Management Science*, 64(3), 1155–1170.\[16\]\[17\]
- DOI: 10.1287/mnsc.2016.2643 · OA: preprint (https://marketing.wharton.upenn.edu/wp-content/uploads/2020/07/Dietvorst-Overcoming-Algorithm-Aversion.pdf). \[16\]
- Streszczenie: Eksperymenty prognostyczne z nagrodami; uczestnicy wybierali między własną prognozą a algorytmem. Nawet ograniczona możliwość korekty wyraźnie zwiększyła użycie algorytmu i poprawiła wyniki.\[18\] To argument za „akceptuj/odrzuć zmianę”, a nie za „AI napisze za ciebie”.

**E05** · M1 · Kryt. 3 · AI pomaga najbardziej słabszym, ekspertom niewiele · **NIUANSUJE** · ✔
- Cytat: "Access to the tool increases productivity, as measured by issues resolved per hour, by 14% on average, including a 34% improvement for novice and low-skilled workers but with minimal impact on experienced and highly skilled workers." Glosa: +14% średnio, +34% dla nowicjuszy, minimalny efekt u doświadczonych.\[19\]
- Miejsce: Abstract (NBER WP 31161).
- Źródło: Brynjolfsson, E., Li, D., Raymond, L. (2025). Generative AI at Work. *Quarterly Journal of Economics*, 140(2), 889–942.\[20\]
- DOI: 10.1093/qje/qjae044 · OA: tak (NBER w31161; arXiv 2304.11771).\[20\]\[21\]
- Streszczenie: Rozłożone w czasie wdrożenie asystenta GenAI u 5 179 konsultantów obsługi klienta (wersja QJE: 5 172 i +15%).\[21\]\[22\] Zyski skupiły się u mniej doświadczonych, u najlepszych efekt był bliski zera.\[23\] Dla Sentinela: redakcja AI pomoże najbardziej słabszym autorom raportów, ekspertowi głównie oszczędzi czas.

### Moduł 2 — Projekty (Monte Carlo + LLM jako tłumacz)

**E06** · M2 · Kryt. 2 · LLM „wyjaśnia decyzje” · **PODWAŻA** (kluczowy kontrdowód) · ✔
- Cytat: "While we observed complementary improvements from AI augmentation, they were not increased by explanations. Rather, explanations increased the chance that humans will accept the AI's recommendation, regardless of its correctness." Glosa: wyjaśnienia nie poprawiły wyników zespołu; zwiększyły akceptację rekomendacji niezależnie od poprawności.\[24\]
- Miejsce: Abstract.
- Źródło: Bansal, G., Wu, T., Zhou, J., Fok, R., Nushi, B., Kamar, E., Ribeiro, M.T., Weld, D.S. (2021). Does the Whole Exceed its Parts? The Effect of AI Explanations on Complementary Team Performance. *Proc. CHI '21*.\[24\]
- arXiv: 2006.14779 · OA: tak.
- Streszczenie: Badania mieszane na trzech zbiorach danych, gdzie AI miała trafność porównywalną z ludźmi. Zespół człowiek+AI był lepszy od każdego z osobna, ale wyjaśnienia tego nie poprawiły, a zwiększyły ślepe przyjmowanie rekomendacji.\[24\] Pop-up „Dlaczego?” w Sentinelu musi więc pokazywać niepewność (rozkład z Monte Carlo) i alternatywy.

**E07** · M2 · Kryt. 1, 2 · Najpierw własna ocena, potem rekomendacja (cognitive forcing) · **WSPIERA (z kosztem)** · ✔
- Cytat: "People supported by AI-powered decision support tools frequently overrely on the AI: they accept an AI's suggestion even when that suggestion is wrong." Glosa: ludzie często przyjmują sugestię AI, nawet błędną.\[25\]
- Cytat 2: "The results demonstrate that cognitive forcing significantly reduced overreliance compared to the simple explainable AI approaches. However, there was a trade-off: people assigned the least favorable subjective ratings to the designs that reduced the overreliance the most." Glosa: wymuszanie myślenia ogranicza nadmierne zaufanie, ale użytkownicy oceniają je najgorzej.\[25\]
- Miejsce: Abstract.
- Źródło: Buçinca, Z., Malaya, M.B., Gajos, K.Z. (2021). To Trust or to Think: Cognitive Forcing Functions Can Reduce Overreliance on AI in AI-assisted Decision-making. *Proc. ACM Hum.-Comput. Interact.* 5(CSCW1).\[25\]
- DOI: 10.1145/3449287 · arXiv: 2102.09692 · OA: tak (CC BY 4.0).\[25\]
- Streszczenie: Eksperyment (N=199) porównał trzy interwencje „cognitive forcing” z dwoma prostymi wariantami XAI i warunkiem bez AI. Interwencje istotnie zmniejszyły nadmierne poleganie na AI, głównie u osób z wysoką „potrzebą poznania”.\[25\] Uzasadnia krok „Twoja ocena ryzyka terminu?” przed pokazaniem wyniku symulacji.

**E08** · M2, M6 · Kryt. 1, 4 · AI liczy i przygotowuje, człowiek zatwierdza („machine-in-the-loop”) · **WSPIERA** · ✔
- Cytat: "We find little preference for full AI control and a strong preference for machine-in-the-loop designs, in which humans play the leading role." Glosa: ludzie nie chcą pełnej kontroli AI; wolą projekty, w których prowadzi człowiek.\[26\]
- Cytat 2: "Among the four factors, trust is the most correlated with human preferences of optimal human-machine delegation." Glosa: zaufanie najsilniej koreluje z preferowanym poziomem delegowania.\[26\]
- Miejsce: Abstract.
- Źródło: Lubars, B., Tan, C. (2019). Ask Not What AI Can Do, But What AI Should Do: Towards a Framework of Task Delegability. *NeurIPS 2019*, s. 57–67.\[27\]
- arXiv: 1902.03245 · OA: tak; dane: delegability.github.io.\[28\]
- Streszczenie: Cztery czynniki delegowania (motywacja, trudność, ryzyko, zaufanie); zbiór 100 zadań i ankieta. Respondenci rzadko wybierali pełną automatyzację.\[26\] To bezpośredni wzór dla ankiety (sekcja D) i skali „AI sama / AI z człowiekiem / tylko człowiek”.

**E09** · M2 · Kryt. 1 · LLM bez autonomii wykonawczej · **PODWAŻA / kontrast** (wizja „agentowego PM”) · ✔
- Cytat: "They will work like a "junior project manager", or an "intern project manager" collaboratively with software teams. We introduce four working modes, with varying autonomy levels to choose from, based on the SPM task." Glosa: agenci mają działać jak „junior PM” w czterech trybach autonomii.\[29\]
- Miejsce: Abstract.
- Źródło: Assalaarachchi, L.I., Masood, Z., Hoda, R., Grundy, J. (2026). Toward Agentic Software Project Management: A Vision and Roadmap. Preprint przyjęty na warsztat AGENT @ ICSE 2026.\[29\]
- arXiv: 2601.16392 · OA: tak (CC BY-NC-ND 4.0).\[29\]
- Streszczenie: Wizja, nie badanie empiryczne: wieloagentowy „Agentic PM” z czterema trybami autonomii, uzasadnionymi etyką, rozliczalnością i zaufaniem; człowiek jako „strategic leader” i „coach”.\[29\] Na obronie: kierunek przeciwny do Sentinela, który daje mniej autonomii i twardy podział (liczby z symulacji, język z LLM).

**E10** · M2, M6 · Sentinel jako prototyp badawczy · **WSPIERA** (stan wiedzy „eksploracyjny”) · ✔
- Cytat: "The analysis reveals a clear dominance of OpenAI's GPT in the included studies but relying primarily on prompt engineering, suggesting that research in this area remains at an exploratory stage." Glosa: badania GenAI w zarządzaniu projektami IT są wciąż eksploracyjne.\[30\]
- Miejsce: Abstract (arXiv).
- Źródło: Anghel, I., Cioara, T. (2026). A systematic review of generative AI usage for IT project management. arXiv:2604.21958. Wersja recenzowana: Generative AI for IT Project Management: A Systematic Review and Future Research Agenda. *Systems* 14(6), 722 (22.06.2026).\[31\]\[32\]
- DOI: 10.48550/arXiv.2604.21958; 10.3390/systems14060722 · OA: tak.
- Streszczenie: Przegląd PRISMA (Politechnika Kluż-Napoka) technik, zastosowań i integracji GenAI z narzędziami PM. Wskazuje trzy kierunki: agentów dla grup procesów, agentów dla ról oraz hybrydowe sieci z orkiestracją kierowaną przez człowieka. Wersja w *Systems* dodaje przegląd platform komercyjnych i open source.\[30\]\[32\]

**E11** · M2, M3, M6 · Kryt. 1 · Człowiek zatwierdza, może odrzucić lub odwrócić wynik · **WSPIERA (z ostrzeżeniem)** · ✔ (przedruki; potwierdź na EUR-Lex)
- Cytat (art. 14 ust. 4 lit. b): "to remain aware of the possible tendency of automatically relying or over-relying on the output produced by a high-risk AI system (automation bias), in particular for high-risk AI systems used to provide information or recommendations for decisions to be taken by natural persons;" Glosa: nadzorujący ma być świadomy skłonności do automatycznego polegania na wyniku AI.\[33\]
- Cytat 2 (lit. d): "to decide, in any particular situation, not to use the high-risk AI system or to otherwise disregard, override or reverse the output of the high-risk AI system;" Glosa: człowiek musi móc zignorować, nadpisać lub odwrócić wynik AI.\[33\]
- Źródło: Rozporządzenie (UE) 2024/1689 (AI Act), art. 14. URL: https://eur-lex.europa.eu/eli/reg/2024/1689/oj · OA: tak.
- Streszczenie: Art. 14 dotyczy systemów wysokiego ryzyka, więc dla Sentinela to wzorzec dobrej praktyki, nie obowiązek. Jedyny przepis AI Act, który nazywa błąd poznawczy (automation bias).\[34\] Łączy się z E06/E07: samo „kliknij zatwierdź” nie jest skutecznym nadzorem.

**E12** · M2 · Archiwum decyzji · **WSPIERA** · ✔ (przedruk; potwierdź na EUR-Lex)
- Cytat (art. 12 ust. 1): "High-risk AI systems shall technically allow for the automatic recording of events (logs) over the lifetime of the system." Glosa: systemy wysokiego ryzyka mają technicznie umożliwiać automatyczne rejestrowanie zdarzeń (logów) przez cały cykl życia.
- Źródło: AI Act, art. 12 (Record-keeping), przedruk artificialintelligenceact.eu, zgodny z innymi przedrukami; ta sama strona podaje stosowanie od 2.12.2027 dla systemów z Załącznika III.

**E13** · M2 · Wyjaśnienia kontrastowe („dlaczego A, a nie B”) · **WSPIERA** · ✔ (abstrakt); teza o kontrastowości ✖
- Cytat: "it is fair to say that most work in explainable artificial intelligence uses only the researchers' intuition of what constitutes a `good' explanation." Glosa: większość prac XAI opiera się na intuicji badaczy.\[35\]
- Miejsce: Abstract.
- Źródło: Miller, T. (2019). Explanation in Artificial Intelligence: Insights from the Social Sciences. *Artificial Intelligence*, 267, 1–38. arXiv: 1706.07269 · OA: tak.\[35\]
- Streszczenie: Przegląd filozofii i psychologii wyjaśniania.\[35\] Główne tezy (do zweryfikowania w pełnym tekście): wyjaśnienia są kontrastowe, selektywne i społeczne. Uzasadnia porównanie „zastępstwo vs przesunięcie terminu” zamiast pojedynczego uzasadnienia.

### Moduł 3 — Finanse (AI streszcza, nigdy nie zatwierdza ani nie zmienia liczb)

**E14** · M3 · Kryt. 2, 3 · LLM nie liczy i nie zmienia liczb · **WSPIERA** · ✔
- Cytat: "Notably, GPT-4-Turbo used with a retrieval system incorrectly answered or refused to answer 81% of questions." Glosa: GPT-4-Turbo z wyszukiwaniem odpowiedział błędnie lub odmówił w 81% pytań.\[36\]
- Cytat 2: "We find that all models examined exhibit weaknesses, such as hallucinations, that limit their suitability for use by enterprises." Glosa: wszystkie modele miały słabości ograniczające użycie w firmach.\[36\]
- Miejsce: Abstract.
- Źródło: Islam, P., Kannappan, A., Kiela, D., Qian, R., Scherrer, N., Vidgen, B. (2023). FinanceBench: A New Benchmark for Financial Question Answering. arXiv:2311.11944 · OA: tak.\[36\]
- Streszczenie: Benchmark 10 231 pytań o spółki publiczne; 16 konfiguracji modeli testowano na 150 przypadkach z ręczną oceną 2 400 odpowiedzi.\[36\] Długi kontekst poprawiał wyniki, ale nie do poziomu pracy bez nadzoru.\[37\]\[38\] Zastrzeżenie: modele z 2023 r.; wniosek architektoniczny (liczby z kodu) pozostaje aktualny, bo błąd w finansach jest kosztowny i trudny do wykrycia.

**E15** · M3 · Kryt. 3 · „Prosta matematyka” poza granicą · **WSPIERA** · ✔
- Cytat: "Some unexpected tasks (like idea generation) are easy for AIs, while other tasks that seem to be easy for machines to do (like basic math) are challenges for some LLMs." Glosa: generowanie pomysłów jest łatwe dla AI, a prosta matematyka bywa problemem.\[12\]
- Miejsce: Dell'Acqua i in. 2023 (E02), Introduction, s. 4 WP.

**E16** · M3 · Przesunięcia budżetu czekają na człowieka · **WSPIERA (rynek idzie w tę stronę)** · ✔ (przedruk komunikatu Microsoft)
- Cytat: "Copilot prepares the work while users retain control of review, approval, and posting. Nothing is posted automatically to an ERP or system of record without approval." Glosa: Copilot przygotowuje pracę, człowiek zatwierdza; nic nie trafia do ERP bez zgody.\[39\]
- Źródło: Microsoft 365 Copilot: New accounting capabilities in Excel and Cowork (przedruk Message Center, M365 Admin/handsontek, 2026); preview od końca października 2026, GA 13 listopada 2026.\[39\]
- URL: https://m365admin.handsontek.net/microsoft-365-copilot-new-accounting-capabilities-excel-cowork/ · OA: tak.
- Streszczenie: Komunikat produktowy, nie badanie. Dostawca sam przyjmuje zasadę „AI przygotowuje, człowiek zatwierdza”, a ślad audytowy jest opcjonalny i na razie tylko w Excelu.\[39\] W Sentinelu zatwierdzenie wymusza architektura, nie konfiguracja.

**E17** · M3, M6 · Kryt. 5 · Predykcja ≠ osąd · **WSPIERA** · ✖ cytat niezweryfikowany
- Źródło: Agrawal, A., Gans, J., Goldfarb, A. (2018). *Prediction Machines: The Simple Economics of Artificial Intelligence*. Harvard Business Review Press (nie OA).
- Streszczenie (do sprawdzenia): AI obniża koszt predykcji, więc rośnie wartość osądu (judgment), czyli określania wartości wyników i kompromisów. Monte Carlo daje predykcję, wybór interwencji to osąd człowieka. Przed cytowaniem znajdź otwartą wersję artykułu autorów (NBER).

### Moduł 4 — Ludzie (funkcja „celowo nie istnieje”)

**E18** · M4 · Kryt. 4 · Brak oceny wydajności pracowników · **WSPIERA** · ✔ (przedruki; potwierdź na EUR-Lex)
- Cytat (Załącznik III pkt 4 lit. b): "AI systems intended to be used to make decisions affecting terms of work-related relationships, the promotion or termination of work-related contractual relationships, to allocate tasks based on individual behaviour or personal traits or characteristics or to monitor and evaluate the performance and behaviour of persons in such relationships." Glosa: AI do monitorowania i oceny wydajności i zachowania pracowników to system wysokiego ryzyka.\[2\]
- Źródło: Rozporządzenie (UE) 2024/1689, Załącznik III, pkt 4(b).
- Streszczenie: Po zmianie rozporządzeniem (UE) 2026/1744 (Dz.Urz. 24.07.2026, w mocy od 27.07.2026) wymogi rozdziału III stosuje się do takich systemów od 2 grudnia 2027 r. zamiast 2 sierpnia 2026 r.; treść Załącznika III się nie zmieniła.\[6\]\[40\] Na obronie (2.12.2026) mów: „obowiązki będą stosowane od grudnia 2027”.

**E19** · M4 · Kryt. 4, 6 · Brak analizy nastroju lub emocji z komunikatów zespołu · **WSPIERA** · ✔ (przedruki; potwierdź na EUR-Lex)
- Cytat (art. 5 ust. 1 lit. f): "the placing on the market, the putting into service for this specific purpose, or the use of AI systems to infer emotions of a natural person in the areas of workplace and education institutions, except where the use of the AI system is intended to be put in place or into the market for medical or safety reasons;" Glosa: zakaz używania AI do wnioskowania o emocjach osób w miejscu pracy (wyjątki: medyczne i bezpieczeństwa).\[41\]
- Streszczenie: Zakaz obowiązuje od 2 lutego 2025 r. i Omnibus go nie przesunął.\[3\]\[42\] Definicja „systemu rozpoznawania emocji” opiera się na danych biometrycznych,\[41\] więc analiza sentymentu samego tekstu jest prawnie dyskusyjna, ale projektowo Sentinel jej nie robi (por. E20). Moduł 2 parsuje statusy zespołu, więc warto zapisać w schemacie JSON brak pól nastroju i emocji.

**E20** · M4 · Kryt. 4 · Brak rankingu ludzi przy zastępstwach · **WSPIERA** · ✔
- Cytat: "We find that algorithmic control in the workplace operates through six main mechanisms, which we call the “6 Rs”—employers can use algorithms to direct workers by restricting and recommending, evaluate workers by recording and rating, and discipline workers by replacing and rewarding." Glosa: kontrola algorytmiczna działa przez „6R”: ograniczanie, rekomendowanie, rejestrowanie, ocenianie, zastępowanie i nagradzanie.\[43\]
- Miejsce: Abstract.
- Źródło: Kellogg, K.C., Valentine, M.A., Christin, A. (2020). Algorithms at Work: The New Contested Terrain of Control. *Academy of Management Annals*, 14(1), 366–410.\[44\]
- DOI: 10.5465/annals.2018.0174 · OA: kopia autorska (angelechristin.com), NSF PAR.\[43\]
- Streszczenie: Przegląd interdyscyplinarny z perspektywy teorii procesu pracy („contested terrain”, Edwards 1979), z opisem oporu pracowników („algoactivism”).\[43\] Interwencja „zastąp nieobecną osobę” jest blisko „replacing”, więc symulacja powinna operować na rolach i dostępności, nie na rankingu ludzi.

**E21** · M4 · Kryt. 4 · Metryka przestaje mierzyć, gdy staje się celem · **WSPIERA** · ✔ (skan PDF)
- Cytat: "When a measure becomes a target, it ceases to be a good measure." Glosa: gdy miara staje się celem, przestaje być dobrą miarą.
- Miejsce: s. 308.
- Źródło: Strathern, M. (1997). 'Improving ratings': audit in the British University system. *European Review*, 5(3), 305–321; oryginał: Goodhart, C. (1975).
- Streszczenie: Brzmienie sprawdzone w skanie PDF artykułu z 1997 r. Strathern przypisuje to sformułowanie prawa Goodharta Keithowi Hoskinowi (1996), więc jest to uogólnienie prawa Goodharta, a nie słowa samego Goodharta.

**E22** · M4 · Kryt. 4, 5 · Bezpieczeństwo psychologiczne jako powód braku oceny · **WSPIERA** · ✔ (abstrakt)
- Cytat: "Results of a study of 51 work teams in a manufacturing company… show that team psychological safety is associated with learning behavior, but team efficacy is not… learning behavior mediates between team psychological safety and team performance." Glosa: w 51 zespołach bezpieczeństwo psychologiczne wiązało się z uczeniem się zespołu, a uczenie się pośredniczyło między nim a wynikami.
- Miejsce: Abstract.
- Źródło: Edmondson, A. (1999). Psychological Safety and Learning Behavior in Work Teams. *Administrative Science Quarterly*, 44(2), 350–383. DOI: 10.2307/2666999 (nie OA).
- Streszczenie: Badanie terenowe zespołów w firmie produkcyjnej; ankiety oddało 51 z 53 zespołów (86% odpowiedzi). Ciągła ocena przez AI zniechęca do zgłaszania problemów, od których zależą dane wejściowe do symulacji ryzyka.

### Moduł 5 — Uprawnienia AI („mniej narzędzi”)

**E23** · M5 · Kryt. 1, 6 · LLM bez narzędzi, tylko walidowany JSON, zero wykonania · **WSPIERA** · ✔
- Cytat: "Excessive Agency is the vulnerability that enables damaging actions to be performed in response to unexpected, ambiguous or manipulated outputs from an LLM, regardless of what is causing the LLM to malfunction." Glosa: przez Excessive Agency zmanipulowany lub błędny wynik LLM prowadzi do szkodliwych działań.\[7\]
- Cytat 2: "The root cause of Excessive Agency is typically one or more of: excessive functionality; excessive permissions; excessive autonomy." Glosa: przyczyny to nadmiar funkcji, uprawnień i autonomii.\[7\]
- Cytat 3: "eliminating excessive autonomy by requiring the user to manually review and hit 'send' on every mail drafted by the LLM extension." Glosa: autonomię ogranicza ręczny przegląd i kliknięcie „wyślij”.\[7\]\[45\]
- Miejsce: LLM06:2025, sekcje Description, Common Examples of Risks, Example Attack Scenarios.
- Źródło: OWASP Gen AI Security Project (2025). OWASP Top 10 for LLM Applications 2025 – LLM06:2025 Excessive Agency.
- URL: https://genai.owasp.org/llmrisk/llm062025-excessive-agency/ · OA: tak.
- Streszczenie: Standard branżowy; wśród wyzwalaczy wymienia halucynacje oraz bezpośrednią i pośrednią prompt injection.\[7\] Sentinel spełnia wszystkie trzy zalecenia jednocześnie. Według źródeł wtórnych w edycji 2026 kategoria awansowała na LLM03:2026, więc zawsze podawaj sufiks roku.\[46\]

**E24** · M5 · Kryt. 6 · Dane wejściowe traktowane jako niezaufane · **WSPIERA** · ✖ cytat niezweryfikowany
- Źródło: OWASP (2025). LLM01:2025 Prompt Injection, genai.owasp.org (sprawdź adres).
- Streszczenie: Prompt injection, w tym pośrednia (instrukcje ukryte w przetwarzanym dokumencie), jest pozycją nr 1. Raport do redakcji lub status może zawierać wstrzyknięte polecenia; brak narzędzi (E23) ogranicza skutki do błędnego tekstu, który wychwytuje walidacja schematu i kontrola encji (E03).

**E25** · M5 · Uprawnienia agenta = uprawnienia użytkownika (wzorzec rynkowy) · **NIUANSUJE** · ✔ (Atlassian Community)
- Cytat: "Rovo agents can only operate within the permissions of user interacting with them." Glosa: agenci Rovo działają tylko w granicach uprawnień użytkownika.\[47\]
- Źródło: Atlassian Community, „Evaluating Rovo? Three things you need to know about security and data governance”.\[47\]
- URL: https://community.atlassian.com/forums/Atlassian-AI-Rovo-discussions/Evaluating-Rovo-Three-things-you-need-to-know-about-security-and/td-p/3085845 · OA: tak.
- Streszczenie: Least privilege „dziedziczone” po użytkowniku to standard rynkowy, ale agent nadal może zrobić wszystko, co użytkownik.\[48\] W Sentinelu LLM ma zero uprawnień niezależnie od wywołującego.

**E26** · M5, M6 · Zarządzanie ryzykiem AI jako proces · **WSPIERA** · ✖ cytat niezweryfikowany
- Źródło: NIST (2023). AI Risk Management Framework (AI RMF 1.0), NIST AI 100-1. DOI: 10.6028/NIST.AI.100-1 · OA: tak.
- Streszczenie: Cztery funkcje: GOVERN, MAP, MEASURE, MANAGE. „Mapa granic” odpowiada MAP, archiwum decyzji GOVERN/MANAGE. Przepisz definicje z sekcji 5 PDF.

### Moduł 6 — Mapa granic (procesy × 6 kryteriów)

**E27** · M6 · wszystkie kryteria · Macierz zamiast „AI tylko do oszczędzania czasu” · **NIUANSUJE / WSPIERA** · ✔
- Cytat: "Using a more comprehensive paradox theory perspective, we argue that, in the management domain, augmentation cannot be neatly separated from automation." Glosa: w zarządzaniu augmentacji nie da się czysto oddzielić od automatyzacji.\[49\]
- Cytat 2: "Overemphasizing either augmentation or automation fuels reinforcing cycles with negative organizational and societal outcomes." Glosa: przesadne nastawienie na jedno lub drugie uruchamia negatywne sprzężenia.\[50\]
- Miejsce: Abstract.
- Źródło: Raisch, S., Krakowski, S. (2021). Artificial Intelligence and Management: The Automation–Augmentation Paradox. *Academy of Management Review*, 46(1), 192–210.\[50\]
- DOI: 10.5465/amr.2018.0072 · OA: tak (Archive ouverte UNIGE).\[1\]
- Streszczenie: Artykuł teoretyczny wychodzący od trzech książek biznesowych zalecających „augmentację zamiast automatyzacji”. Z perspektywy teorii paradoksu oba tryby są współzależne w czasie i przestrzeni.\[1\] Odpowiada wprost na tezę promotora: ograniczenie AI do zadań „oszczędzających czas” przesuwa napięcie, a nie je usuwa.

**E28** · M6 · Kryt. 1 · Różne poziomy automatyzacji dla etapów (pozyskanie, analiza, decyzja, działanie) · **WSPIERA** · ✖ cytat niezweryfikowany
- Źródło: Parasuraman, R., Sheridan, T.B., Wickens, C.D. (2000). A model for types and levels of human interaction with automation. *IEEE Trans. SMC – Part A*, 30(3), 286–297. DOI: 10.1109/3468.844354.
- Streszczenie: Cztery funkcje (information acquisition, information analysis, decision selection, action implementation), każda z własnym poziomem automatyzacji. Sentinel: wysoka automatyzacja analizy, niska wyboru, zerowa wykonania. Najlepszy diagram na slajd architektury.

**E29** · M6 · Kryt. 2 · Kalibracja zaufania · **WSPIERA** · ✖ cytat niezweryfikowany
- Źródło: Lee, J.D., See, K.A. (2004). Trust in Automation: Designing for Appropriate Reliance. *Human Factors*, 46(1), 50–80. DOI: 10.1518/hfes.46.1.50_30392.
- Streszczenie: Celem projektowania jest „odpowiednie poleganie” (appropriate reliance), czyli zaufanie skalibrowane do rzeczywistej niezawodności. Łączy się z E06/E07.

**E30** · M6 · Kryt. 1, 2 · Człowiek „w pętli”, nie tylko „na pętli” · **WSPIERA / ostrzeżenie** · ✖ cytaty niezweryfikowane
- Źródła: Endsley, M.R., Kiris, E.O. (1995). The Out-of-the-Loop Performance Problem and Level of Control in Automation. *Human Factors*, 37(2), 381–394. Skitka, L.J., Mosier, K.L., Burdick, M. (1999). Does automation bias decision-making? *Int. J. Human-Computer Studies*, 51(5), 991–1006.
- Streszczenie: Przy pełnej automatyzacji spada świadomość sytuacyjna i trudniej przejąć kontrolę po awarii; pośrednie poziomy łagodzą efekt. Osoby z „pomocą automatyczną” popełniały błędy pominięcia i wykonania, gdy automat się mylił. Kryterium 1 musi więc uwzględniać, czy człowiek ma jeszcze kompetencję, by ocenić wynik.

**E31** · M6 · Kryt. 5 („smak”) · Wartości, relacje i wiedza ukryta: „NIE” lub „z człowiekiem” · **WSPIERA (teoria)** · ✖ cytat niezweryfikowany
- Źródło: Autor, D.H. (2014). Polanyi's Paradox and the Shape of Employment Growth. NBER Working Paper 20485 (OA).
- Streszczenie: Wiele zadań opiera się na wiedzy ukrytej („we can know more than we can tell”, Polanyi 1966), której nie da się skodyfikować. Artykuł jest sprzed LLM, które częściowo „obchodzą” paradoks, ucząc się z przykładów (por. E02). Na obronie: „smak” to granica normatywna, nie dowiedziona techniczna niemożność.

**E32** · M6 · Kryt. 6 · **WSPIERA** · ✖ cytat niezweryfikowany
- Źródło: RODO, Rozporządzenie (UE) 2016/679, art. 9. URL: https://eur-lex.europa.eu/eli/reg/2016/679/oj. \[51\]
- Streszczenie: Art. 9 ust. 1 zakazuje przetwarzania m.in. danych o zdrowiu, przynależności związkowej i danych biometrycznych, z wyjątkami z ust. 2. Interwencja „zastąp nieobecną osobę” nie powinna przetwarzać powodu nieobecności; wystarczy flaga „niedostępny”.

**E33** · M6 · Kryt. 6, 1 · **WSPIERA** · ✖ (norma płatna)
- Źródło: ISO/IEC 42001:2023, Information technology — Artificial intelligence — Management system. Publicznie dostępny jest tylko opis zakresu na iso.org.
- Streszczenie: Norma systemu zarządzania AI w strukturze podobnej do ISO 27001. Cytuj tylko tytuł i opis zakresu, bez klauzul.

**E34** · M6, wszystkie moduły · Pop-up „Evidence” jako narzędzie budowania kompetencji AI · **WSPIERA** · ✔ (wersja pierwotna) / ✖ (po zmianie)
- Cytat (pierwotny art. 4): "Providers and deployers of AI systems shall take measures to ensure, to their best extent, a sufficient level of AI literacy of their staff and other persons dealing with the operation and use of AI systems on their behalf". Glosa: obowiązek zapewnienia „wystarczającego poziomu” kompetencji AI personelu.\[41\]
- Streszczenie: Od 27.07.2026 rozporządzenie 2026/1744 zamieniło ten obowiązek na obowiązek „wspierania/promowania” rozwoju kompetencji; źródła wtórne różnią się co do słowa.\[5\]\[40\] Według jednego z nich nowy tekst „does not require providers or deployers to guarantee any specific level of AI literacy of any individual”.\[42\] W pop-upie podaj obie wersje z datami albo nowy tekst z EUR-Lex.

### Przypisanie do kryteriów mapy granic

| Kryterium | Najmocniejsze dowody | Uwaga dla obrony |
|---|---|---|
| 1. Odwracalność i stawka | E04, E08, E11, E28, E30 | Tracked changes = pełna odwracalność; przesunięcie budżetu = niska, więc „z człowiekiem” |
| 2. Weryfikowalność | E03, E06, E07, E14, E29 | Kod sprawdza encje i liczby; wyjaśnienia nie zastępują weryfikacji (E06) |
| 3. Jagged frontier | E01, E02, E05, E15 | Język: tak; liczby, nowy osąd, strategia: nie lub z człowiekiem |
| 4. Wpływ na ludzi i pieniądze | E18, E19, E20, E22 | Najmocniejsze oparcie prawne; moduł „celowo NIE” |
| 5. „Smak” | E17, E27, E31 | Najsłabsze empirycznie; przedstaw jako granicę normatywną |
| 6. Wrażliwość danych | E23, E24, E32, E33 | Brak narzędzi = brak kanału eksfiltracji |

### Prawo cytatu (repozytorium GitHub i slajdy)

**E35** · ✔
- Cytat: „Wolno przytaczać w utworach stanowiących samoistną całość urywki rozpowszechnionych utworów oraz rozpowszechnione utwory plastyczne, utwory fotograficzne lub drobne utwory w całości, w zakresie uzasadnionym celami cytatu, takimi jak wyjaśnianie, polemika, analiza krytyczna lub naukowa, nauczanie lub prawami gatunku twórczości.”\[52\]
- Źródło: art. 29 ustawy z 4 lutego 1994 r. o prawie autorskim i prawach pokrewnych.\[53\]
- Wniosek: Krótkie cytaty z opublikowanych artykułów z oznaczeniem źródła są dozwolone, jeśli: utwór był rozpowszechniony; Sentinel i prezentacja są „samoistną całością”; cytat służy wyjaśnianiu lub analizie krytycznej; podano autora i źródło (art. 34).\[54\] Komentatorzy podkreślają ścisły związek cytatu z własnym wywodem, więc każdy pop-up powinien mieć własne zdanie „co z tego wynika dla Sentinela”.\[55\] Artykuły na CC BY (np. E03, E07) można cytować także na podstawie licencji; przy CC BY-NC-ND (E09, E14) wystarcza prawo cytatu. Akty prawne (AI Act, RODO) nie są przedmiotem prawa autorskiego (art. 4). To nie jest opinia prawna.

---

## B. Przegląd rynku (stan: listopad 2026)

**Wniosek:** Teza „takich narzędzi jeszcze nie ma” jest fałszywa w wersji „nie ma AI w zarządzaniu firmą”, ale prawdziwa w wersji „nie ma narzędzia, które jawnie i z uzasadnieniem naukowym projektuje granice dla AI”. Proponowane sformułowanie na obronę: „AI w procesach zarządczych już jest, ale granice są w nich ustawieniem administratora, a nie decyzją projektową opartą na dowodach”.

| Narzędzie | Co robi AI | Human-in-the-loop i zatwierdzanie | Uprawnienia | Audyt | Weryfikacja |
|---|---|---|---|---|---|
| Microsoft 365 Copilot (Excel/Cowork, funkcje księgowe) | Uzgodnienia kont, zapisy księgowe, analiza odchyleń, budżet/forecast | „Nothing is posted automatically to an ERP or system of record without approval” | Tylko treści dostępne dla użytkownika, etykiety wrażliwości | Ślad audytowy opcjonalny, w Excelu (Cowork planowany); Show Changes oddziela edycje Copilota od ludzkich | ✔ (przedruki komunikatu)\[39\]\[56\] |
| Atlassian Rovo (Jira/Confluence) | Agenci w zgłoszeniach i przejściach workflow, Rovo Studio | W czacie potwierdzenie przed narzędziami zmieniającymi dane; według źródeł wtórnych bez potwierdzenia w regułach automatyzacji | Domyślnie uprawnienia użytkownika; opcjonalne konto agenta | Zdarzenie „Invoked Rovo agent” wymaga Atlassian Guard Premium | ✔ częściowo\[48\]\[57\]\[58\] |
| Asana AI Studio, Notion AI, monday AI, Salesforce Agentforce | Workflow AI, streszczenia, agenci | Nie zweryfikowano | — | — | ✖ sprawdzić w dokumentacji |

**Gdzie Sentinel jest inny:**
1. **Zatwierdzenie z architektury, nie z konfiguracji.** U Microsoftu i Atlassiana human-in-the-loop zależy od ustawień, a w automatyzacjach Rovo może zniknąć;\[48\] w Sentinelu LLM fizycznie nie może wykonać działania (E23).
2. **Liczby nie pochodzą z LLM.** Copilot generuje formuły i zapisy do sprawdzenia;\[59\] Sentinel liczy w Monte Carlo i deterministycznym kodzie (E14).
3. **Funkcje celowo nieistniejące.** Żaden ze sprawdzonych produktów nie komunikuje świadomej rezygnacji z funkcji (E18–E22).
4. **Dowód przy każdej funkcji.** Produkty komercyjne podają certyfikaty zgodności (SOC 2, ISO), a nie dowody naukowe za i przeciw decyzji projektowej.\[47\]

**Prognoza Gartnera (80% zadań PM wyeliminowanych do 2030):** pochodzi z komunikatu prasowego Gartnera z 20.03.2019 („Gartner Says 80 Percent of Today's Project Management Tasks Will Be Eliminated by 2030 as Artificial Intelligence Takes Over”), w którym cytowany jest Daniel Stang, research VP Gartnera. Według zgodnych przedruków (SiliconANGLE, 20.03.2019; ChannelLife, 25.03.2019): „80% of the work of today's project management (PM) discipline will be eliminated as artificial intelligence (AI) takes on traditional PM functions such as data collection, tracking and reporting”. Strony Gartnera nie pobrano bezpośrednio. To prognoza rynkowa, nie dowód: zestaw ją z E10 (badania „exploratory”) i E02 (praca poza granicą pogarsza wyniki). Zauważ też, że Gartner wymienia zbieranie danych, śledzenie i raportowanie, czyli dokładnie zadania, które Sentinel oddaje AI, a nie osąd.

---

## C. Gdzie opublikować ankietę (Facebook / LinkedIn)

**Zastrzeżenie:** Strony grup Facebooka wymagają logowania; liczby członków pochodzą ze źródeł trzecich i są datowane, a regulaminów nie udało się zacytować.

**1. Grupy wymiany ankiet (najwyższa szansa, głównie studenci)**
- **„Ankieta za ankietę”**: facebook.com/groups/ankietybadania/; prowadzi Tabelkomat, zasada wzajemności („Ty wypełnisz mi, ja wypełnię Tobie”).\[60\] Liczba członków nieznana; ankiety są celem grupy.
- **„Uczestnicy badania ankiety (licencjackich, magisterskich)”**: ok. 9 400+ członków według SurveyCircle;\[61\] link po darmowej rejestracji na surveycircle.com; wymagany szablon (temat, grupa docelowa, czas, link SurveyCircle, link oryginalny).\[61\]
- **LinkedIn: „Znaleźć uczestnika ankiety (praca licencjacka, praca magisterska, dysertacja)”**: ok. 300+ członków.\[61\]
- **facebook.com/groups/ankiety/** i **facebook.com/groups/ankietypomagam**: według poradnika magisterna5.pl najpopularniejsze;\[62\]\[63\] nazwy, liczebność i regulamin niezweryfikowane.

**2. HR:** **„HR HRowi HRem”** (prywatna), ok. 20 tys. członków w 2022 r., określana jako największa polska grupa HR.\[64\]\[65\] Inne (bez zweryfikowanych URL i liczb): „I LOVE HR” (wymaga hashtagów), „HR jako Business Partner”, „HR po godzinach”, „HR Inspirations&Networking Poland”, „HR w IT”, „Recruitment Open Community (ROC) Polska”.\[65\]\[66\]

**3. Finanse i księgowość:** największa grupa księgowych miała „ponad 51 tys.” członków (2021, nazwa niepewna, prawdopodobnie „Księgowi – grupa zamknięta”). Inne: „Księgowość spółek”, „Kpir, ryczałt – pomoc w uproszczonej księgowości”, „Biura rachunkowe na zakręcie – grupa wsparcia”.\[67\] „Profesjonalni Księgowi SKwP” wymaga numeru członkowskiego SKwP.\[68\]

**4. Przedsiębiorcy i startupy (bez zweryfikowanych URL i liczb):** „Grupa Przygody Przedsiębiorców”, „Rozmowy o działalności gospodarczej”, „Rozmowy o startupach”, „Grupa Białe Kołnierzyki – o biznesie”.\[69\]

**5. AI:** **„ChatGPT Polska”**: 263 tys. członków według sprzedawcy kursów (deklaracja marketingowa).\[70\] „Sztuczna inteligencja – grupa” (facebook.com/groups/sztucznainteligencja.biz), „Machine & Deep Learning Polska” (facebook.com/groups/machine.learning.polska).\[71\]

**6. Project management:** nie potwierdzono żadnej polskiej grupy PM na Facebooku. „Agile Polska” i „IPMA Polska” to fanpage (ok. 3,2 tys. i 4,8 tys. obserwujących);\[72\]\[73\] lokalne społeczności Agile działają na Meetup (np. Agile Wrocław, ok. 4,8 tys.).\[74\] Najlepiej napisać do administratorów z prośbą o udostępnienie.

**Wskazówki:** w grupach zawodowych najpierw napisz do administratora. W pierwszym zdaniu podaj, kim jesteś (student Politechniki Rzeszowskiej), cel, czas (5 min), anonimowość i wyłącznie edukacyjne wykorzystanie; zaproponuj udostępnienie wyników.\[75\] Nie używaj ankiet wbudowanych w Facebooka, bo pokazują, kto jak głosował.\[76\]\[77\] Przy celu 15–30 osób wystarczą dwie lub trzy grupy zawodowe plus jedna grupa wymiany, z pytaniem filtrującym (sekcja D).

---

## D. Projekt ankiety (Google Forms, PL, ~5 min, N≈15–30)

**Status metodologiczny:** Przy 15–30 respondentach z Facebooka ankieta jest wyłącznie uzupełniającym sondażem opinii i nie pozwala na wnioskowanie statystyczne o populacji menedżerów. Raportuj liczebności i rozkłady, nie testy istotności.

**Instrumenty do zaadaptowania:**
- **Lubars & Tan (2019), E08:** cztery czynniki delegowania i skala podziału pracy człowiek–maszyna; pytania i dane w repozytorium autorów (delegability.github.io).\[26\]\[28\] Najlepsze dopasowanie, pozwala porównać wyniki z oryginałem.
- **Zaufanie do automatyzacji:** Jian, Bisantz i Drury (2000), „Checklist for Trust between People and Automation” (12 pozycji); Körber (2019), Trust in Automation questionnaire. Niezweryfikowane w tym badaniu; użyj maksymalnie 2–3 pozycji i oznacz jako adaptację.
- **Postawy wobec AI:** General Attitudes towards Artificial Intelligence Scale (GAAIS; Schepman i Rodway, 2020), niezweryfikowana; ewentualnie 2–3 pozycje.

**Struktura (ok. 25 pozycji):**
1. **Ekran zgody** (tekst poniżej) z przyciskiem „Wyrażam zgodę i przechodzę dalej”.
2. **Pytanie filtrujące:** „Czy pracujesz lub pracowałeś(-aś) zawodowo w firmie lub organizacji?”; „nie” kieruje do podziękowania lub ścieżki „student”.
3. **Macierz 12 zadań** (AI samodzielnie / AI z człowiekiem / tylko człowiek / nie wiem): redakcja raportu napisanego przez człowieka; wersje raportu dla działów; streszczenie protokołu ze spotkania; zamiana wiadomości statusowych na dane o postępie; prognoza dotrzymania terminu; wybór działania naprawczego w projekcie; streszczenie budżetu i odchyleń; zatwierdzenie przesunięcia budżetu lub wydatku; ocena wydajności pracownika; wybór osoby na zastępstwo; komunikat do zespołu o trudnej decyzji; decyzja strategiczna (np. wejście na nowy rynek).
4. **Waga 6 kryteriów** (1–5, „Jak ważne jest to kryterium, decydując, czy AI może wykonać zadanie?”): odwracalność i stawka; łatwość sprawdzenia wyniku; praca językowa czy liczby i osąd; wpływ na ludzi i pieniądze; wartości, relacje i wyczucie („smak”); wrażliwość danych.
5. **Dwa pytania o mechanizmy Sentinela** (1–5): „Chcę widzieć każdą zmianę wprowadzoną przez AI (tryb śledzenia zmian)”; „Wyjaśnienie AI sprawia, że łatwiej akceptuję jej rekomendację” (testuje efekt z E06).
6. **Pytanie otwarte:** „Gdzie, Twoim zdaniem, AI w firmie nie powinna być używana i dlaczego?”
7. **Metryczka (przedziały):** rola (zarząd / kierownik / PM / specjalista / HR / finanse / inne); staż (<2, 2–5, 6–10, >10 lat); wielkość firmy (1–9, 10–49, 50–249, 250+); częstotliwość używania AI w pracy (nigdy … codziennie). Bez wieku i płci; przy N=20 kombinacja rzadkich cech może umożliwić identyfikację, więc nie publikuj tabel krzyżowych z komórkami poniżej 3.

**Ustawienia Google Forms:** wyłącz „Zbieraj adresy e-mail” i „Ogranicz do 1 odpowiedzi” (wymaga logowania i wiąże odpowiedź z kontem); nie pytaj o nazwę firmy.

**Wzór informacji i zgody:**
> „Nazywam się Kamil Piejko, jestem studentem Politechniki Rzeszowskiej. Ankieta jest częścią projektu zaliczeniowego „AI Driven Project Management” i dotyczy tego, które zadania w firmie można powierzać sztucznej inteligencji. Wypełnienie zajmie ok. 5 minut. Ankieta jest anonimowa: nie zbieram imion, adresów e-mail, nazw firm ani innych danych pozwalających Cię zidentyfikować, a w raporcie pokażę tylko zbiorcze wyniki. Udział jest dobrowolny: możesz przerwać w dowolnym momencie bez podania przyczyny. Prosimy nie wpisywać w pytaniu otwartym danych osobowych ani informacji poufnych o swojej firmie. Zbiorcze wyniki mogą zostać opublikowane w publicznym repozytorium projektu (GitHub) i w prezentacji. Formularz jest obsługiwany przez Google Forms. Kontakt: [adres uczelniany]. Klikając „Wyrażam zgodę”, potwierdzasz, że masz ukończone 18 lat i zgadzasz się na udział.”

**Uwaga RODO:** Dane faktycznie anonimowe nie podlegają RODO (motyw 26), więc kluczowe jest niezbieranie danych identyfikujących i niezachęcanie do ich podawania w pytaniu otwartym. Google technicznie przetwarza metadane (np. IP). Sprawdź, czy uczelnia wymaga zgłoszenia ankiety do komisji etycznej.

**Ograniczenia próby wygodnej z Facebooka:**
1. **Samoselekcja:** odpowiadają osoby zainteresowane AI, zwykle bardziej entuzjastyczne lub bardziej krytyczne niż przeciętna.
2. **Grupy wymiany** przesuwają próbę w stronę studentów;\[78\]\[79\] pytanie filtrujące częściowo to koryguje.
3. **Brak operatu losowania i mianownika**, więc nie da się policzyć wskaźnika odpowiedzi.
4. **N=15–30** daje szerokie przedziały: dla proporcji 50% przy N=25 margines wynosi ok. ±20 pp.
5. **Deklaracje ≠ zachowania:** E06 i E07 pokazują, że ludzie w praktyce polegają na AI bardziej, niż deklarują.
6. **Efekt kolejności:** włącz w Forms „przetasuj kolejność wierszy” w macierzy.

---

## Zastrzeżenia
- **Cytaty oznaczone ✖** (E17, E24, E26, E28–E33) nie zostały porównane z tekstem źródłowym i nie mogą trafić do pop-upów jako dosłowne bez sprawdzenia w PDF.
- **Teksty AI Act** sprawdzono na wiernych przedrukach (EUR-Lex był niedostępny); przed publikacją porównaj z wersją skonsolidowaną po rozporządzeniu 2026/1744.
- **Dane rynkowe** pochodzą częściowo ze źródeł wtórnych; Asana, Notion, monday i Salesforce nie zostały zweryfikowane.
- **Benchmark E14** dotyczy modeli z 2023 r.; wniosek architektoniczny jest aktualny, konkretne odsetki błędów nie opisują dzisiejszych modeli.
- **Własny wynik Sentinela** („LLM wybierający akcje działa jak losowy wybór”) nie był przedmiotem tego badania; przedstaw go jako wynik wstępny, z liczbą przebiegów i metodą porównania.

## Sources

1. [Archive ouverte UNIGE https://archive-ouverte.unige.ch Article scientifique](https://access.archive-ouverte.unige.ch/access/metadata/dd0713db-1880-4c09-9701-52ea58633532/download)
2. [ANNEX III](https://ai-eu-act.eu/annexes/annexes-annex-iii/)
3. [The EU AI Act when an AI is taking your notes](https://getweeve.io/blog/eu-ai-act-ai-notetaker)
4. [Digital Omnibus on AI (Regulation 2026/1744): what changes](https://www.globalsuitesolutions.com/digital-omnibus-ai-regulation-2026-1744/)
5. [EU AI Act Digital Omnibus: What Changed](https://opsiocloud.com/knowledge-base/eu-ai-act-digital-omnibus/)
6. [The Digital Omnibus on AI: What Regulation (EU) 2026/1744 Changed — EU AI Act](https://www.euai-act.com/articles/eu-ai-act-digital-omnibus-2026)
7. [LLM06:2025 Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
8. [Google Scholar](https://scholar.google.com/scholar_lookup?title=Experimental+evidence+on+the+productivity+effects+of+generative+artificial+intelligence&amp=&author=S.+Noy&amp=&author=W.+Zhang&amp=&publication_year=2023&amp=&journal=Science&amp=&pages=187-192&amp=&doi=10.1126/science.adh2586&amp=&pmid=37440646)
9. [\[PDF\] Experimental evidence on the productivity effects of generative artificial intelligence](https://www.semanticscholar.org/paper/Experimental-evidence-on-the-productivity-effects-Noy-Zhang/8d020275181c69e5e768c6ffc40e09710a6f54f1)
10. [Experimental evidence on the productivity effects of generative artificial intelligence](https://bibbase.org/network/publication/noy-zhang-experimentalevidenceontheproductivityeffectsofgenerativeartificialintelligence-2023)
11. [Experimental Evidence on the Productivity Effects of Generative Artificial Intelligence by Shakked Noy, Whitney Zhang :: SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4375283)
12. <https://mitsloan.mit.edu/sites/default/files/2023-10/SSRN-id4573321.pdf>
13. [AI Advocate: Educational Path to Transform Squads to the Future](https://arxiv.org/pdf/2605.03800)
14. [Survey of Hallucination in Natural Language Generation](https://arxiv.org/abs/2202.03629)
15. [Overcoming Algorithm Aversion 1 Running Head: OVERCOMING ALGORITHM AVERSION](https://marketing.wharton.upenn.edu/wp-content/uploads/2020/07/Dietvorst-Overcoming-Algorithm-Aversion.pdf)
16. [Overcoming Algorithm Aversion: People Will Use Imperfect Algorithms If They Can Even Slightly Modify Them: Management Science: Vol 64, No 3](https://dl.acm.org/doi/10.1287/mnsc.2016.2643)
17. [MANAGEMENT SCIENCE Vol. 64, No. 3, March 2018, pp. 1155–1170](https://faculty.wharton.upenn.edu/wp-content/uploads/2016/08/Dietvorst-Simmons-Massey-2018.pdf)
18. [Algorithmic Aversion - The Agile Brand Guide®](https://agilebrandguide.com/wiki/models/algorithmic-aversion/)
19. [Generative AI at Work](https://www.nber.org/papers/w31161)
20. [Generative AI at Work\*](https://academic.oup.com/qje/article/140/2/889/7990658)
21. [fill Generative AI at Work˚ Erik Brynjolfsson Danielle Li Lindsey Raymond](https://arxiv.org/pdf/2304.11771)
22. [NBER WORKING PAPER SERIES GENERATIVE AI AT WORK Erik Brynjolfsson Danielle Li](https://www.nber.org/system/files/working_papers/w31161/w31161.pdf)
23. [(PDF) Generative AI at Work](https://www.researchgate.net/publication/370227920_Generative_AI_at_Work)
24. [Does the Whole Exceed its Parts? The Effect of AI Explanations on Complementary Team Performance](https://arxiv.org/abs/2006.14779)
25. [To Trust or to Think: Cognitive Forcing Functions Can Reduce Overreliance on AI in AI-assisted Decision-making](https://arxiv.org/abs/2102.09692)
26. [Ask Not What AI Can Do, But What AI Should Do: Towards a Framework of Task Delegability](https://arxiv.org/abs/1902.03245)
27. [Ask not what AI can do, but what AI should do](https://dl.acm.org/doi/abs/10.5555/3454287.3454293)
28. [Ask Not What AI Can Do, But What AI Should Do: Towards a Framework of Task Delegability - ADS](https://ui.adsabs.harvard.edu/abs/2019arXiv190203245L/abstract)
29. [Toward Agentic Software Project Management: A Vision and Roadmap](https://arxiv.org/abs/2601.16392)
30. [A systematic review of generative AI usage for IT project management](https://arxiv.org/pdf/2604.21958)
31. [\[2604.21958\] A systematic review of generative AI usage for IT project management](https://arxiv.org/abs/2604.21958)
32. [Generative AI for IT Project Management: A Systematic Review and Future Research Agenda](https://doi.org/10.3390/systems14060722)
33. [Read Article 14: Human oversight](https://legalviz.eu/aia/article/14/)
34. [Automation Bias in the AI Act: On the Legal Implications of Attempting to De-Bias Human Oversight of AI](https://arxiv.org/pdf/2502.10036)
35. [Explanation in Artificial Intelligence: Insights from the Social Sciences](https://arxiv.org/abs/1706.07269)
36. [FinanceBench: A New Benchmark for Financial Question Answering](https://arxiv.org/abs/2311.11944)
37. [FinanceBench: A New Benchmark for Financial Question Answering](https://www.alphaxiv.org/overview/2311.11944v1)
38. [FinanceBench Highlights LLM Limitations in Financial Query Accuracy](https://www.welcome.ai/content/financebench-highlights-llm-limitations-in-financial-query-accuracy)
39. [Microsoft 365 Copilot: New accounting capabilities in Excel and Cowork - M365 Admin](https://m365admin.handsontek.net/microsoft-365-copilot-new-accounting-capabilities-excel-cowork/)
40. [AI Act: obligations in force and delays under omnibus 2026/1744 — ActuIA](https://www.actuia.com/en/news/ai-act-obligations-in-force-and-delays-under-omnibus-2026-1744/)
41. [AI Act, Author at Artificial Intelligence Act](https://artificialintelligenceact.com/author/stephanie-marthinus-hans/)
42. [Digital Omnibus: what the EU AI Act postponed](https://aiactinsight.eu/en/eu-ai-act/digital-omnibus/)
43. [Algorithms at Work: The New Contested Terrain of Control](https://par.nsf.gov/biblio/10195395-algorithms-work-new-contested-terrain-control)
44. [Kellogg, Katherine C; Valentine, Melissa A; Christin, Angèle. Algorithms at Work: The New Contested Terrain of Control (2020)](https://onwork.edu.au/bibitem/2020-Kellogg,Katherine+C-Valentine,Melissa+A-etal-Algorithms+at+Work+The+New+Contested+Terrain+of+Control/)
45. [OWASP PDF v4.2.0a 20241114-202703 OWASP Top 10 for LLM Applications 2025](https://owasp.github.io/www-project-top-10-for-large-language-model-applications/assets/PDF/OWASP-Top-10-for-LLMs-v2025.pdf)
46. [OWASP Top 10 for LLM Applications Guide: 2025 and 2026](https://nhimg.org/owasp-top-10-for-llm-applications-guide)
47. [Evaluating Rovo? Three things you need to know about security and data governance](https://community.atlassian.com/forums/Atlassian-AI-Rovo-discussions/Evaluating-Rovo-Three-things-you-need-to-know-about-security-and/td-p/3085845)
48. [Is Atlassian Rovo safe to let act in Jira and Confluence?](https://greenlitbooks.com/field-notes/is-atlassian-rovo-safe)
49. [Raisch, Sebastian; Krakowski, Sebastian. Artificial Intelligence and Management: The Automation–Augmentation Paradox (2021)](https://onwork.edu.au/bibitem/2021-Raisch,Sebastian-Krakowski,Sebastian-Artificial+Intelligence+and+Management+The+Automation+Augmentation+Paradox/)
50. [Artificial intelligence and management: The automation-augmentation paradox - Stockholm School of Economics](https://research.hhs.se/esploro/outputs/journalArticle/Artificial-intelligence-and-management-The-automation-augmentation/991001480551706056)
51. [Regulation - 2016/679 - EN - gdpr - EUR-Lex](https://eur-lex.europa.eu/eli/reg/2016/679/oj)
52. [Art 29 prawo-autorskie-i-prawa-pokrewne - Ustawa o prawie autorskim i](https://dlajurysty.pl/prawo/art/29prawo-autorskie-i-prawa-pokrewne)
53. [Prawo cytatu](https://contentwriter.pl/prawo-cytatu/)
54. [Kiedy dopuszczalne jest cytowanie cudzego dzieła](https://www.blizejprawa.com/kiedy-dopuszczalne-prawo-cytatu/)
55. [Cytat w utworach naukowych Dr hab. Wojciech Machała Uniwersytet Warszawski](https://fulbright.edu.pl/wp-content/uploads/2020/02/P1_p3_Wojciech-Macha%C5%82a_Cytat-w-utworach-naukowych.pdf)
56. [Excel Copilot Adds Skills, Live Finance Connectors & Tracking](https://windowsforum.com/news/microsoft-copilot-in-excel-adds-skills-live-finance-connectors-and-workbook-change-tracking.430638/)
57. [Rovo Agent Permissions vs CogniRunner Approvals](https://leanzero.net/blog/rovo-agent-permissions-cognirunner-approvals)
58. [Service accounts vs agent identities in Atlassian Cloud](https://www.atlas-bench.com/resources/service-accounts-vs-agent-identities)
59. [Microsoft 365 Roadmap 2025–26: Copilot Agents, Edge AI, Excel GA & Governance](https://windowsforum.com/threads/microsoft-365-roadmap-2025-26-copilot-agents-edge-ai-excel-ga-governance.389265/)
60. [Brak respondentów do pracy dyplomowej? Zobacz, jak ich znaleźć!](https://tabelkomat.pl/blog/jak-zdobyc-respondentow-do-badan-dyplomowych/)
61. [SurveyCircle](https://www.surveycircle.com/en/groups/)
62. [Ankieta do pracy licencjackiej i magisterskiej. Jak przygotować? - Magister na 5](https://magisterna5.pl/ankieta-do-pracy-licencjackiej-magisterskiej/)
63. [Jak zrobić ankietę do pracy dyplomowej w Google? - Magister na 5](https://magisterna5.pl/jak-zrobic-ankiete-do-pracy-dyplomowej-w-google/)
64. [Szybkie wzrosty grup Facebookowych dedykowanych rekrutacji](https://elementapp.ai/blog/szybkie-wzrosty-grup-facebookowych-dedykowanych-rekrutacji/)
65. [Grupy na Facebooku dla HR i Employer Brandingu - How2Hr](https://www.how2hr.pl/grupy-na-facebooku-dla-hr-i-employer-brandingu/)
66. [Rekrutacja na Facebooku - narzędzia i aplikacje.](https://dorisinsocialmedia.com/rekrutacja-na-facebooku/)
67. [Grupy dla księgowych, do których warto dołączyć](https://scanye.pl/blog/grupy-dla-ksiegowych)
68. [Profesjonalni Księgowi SKwP - Stowarzyszenie Księgowych w Polsce Oddział Okręgowy w Warszawie](https://skp-ow.pl/aktualnosc/profesjonalni-ksiegowi-skwp/)
69. [19 grup na Facebooku dla rozwijających się przedsiębiorców - Strona Biznesu](https://stronabiznesu.pl/grupy-na-facebooku-dla-przedsiebiorcow)
70. [Kurs ChatGPT Pro](https://www.exaity.pl/step/chatgpt/)
71. [Społeczności, grupy • Inteligencja.pl](https://inteligencja.pl/spolecznosc/grupy)
72. [IPMA Polska. Zarządzanie Projektami](https://www.facebook.com/ipmapolska/)
73. [Agile Polska](https://web.facebook.com/agilepolska/?_rdc=1&_rdr=#)
74. [Agile Wroclaw](https://meetup.com/AgileWroclaw)
75. [Ankieta w pracy magisterskiej - czym jest, na czym polega, jak przeprowadzić](https://www.praca-magisterska.pl/poradniki/metodologia/ankieta/)
76. [Jak zrobić ankietę na Messengerze i Facebooku](https://www.interankiety.pl/blog/ankieta-messenger-facebook-jak-zrobic/)
77. [Jak zrobić ankietę na Facebooku](https://www.pcarena.pl/blog/jak-zrobic-ankiete-na-facebooku-krok-po-kroku-w-grupach-i-wydarzeniach/)
78. [Ankieta w pracy magisterskiej - kompleksowy poradnik](https://www.licencjackie.pl/blog/ankieta-w-pracy-magisterskiej/)
79. [Gdzie opublikować ankietę do pracy dyplomowej?](https://ankietystudenta.pl/blog/gdzie-opublikowac-ankiete-do-pracy-dyplomowej)
