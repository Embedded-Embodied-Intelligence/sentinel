"""The texts of the v3 research layer (WP19; docs/design/v3-spec.md, sections 1 to 6), merged into
the v2 catalogue (key -> (English, Polish)). The labels the spec quotes are exact; the research
texts themselves (evidence, decisions, the map) come from `sentinel.evidence`."""

from collections.abc import Mapping

CATALOGUE_V3: Mapping[str, tuple[str, str]] = {
    # ---- navigation (section 1)
    "v2.nav.group.work": ("Work", "Praca"),
    "v2.nav.group.rules": ("AI rules", "Zasady AI"),
    "v2.nav.group.other": ("Other", "Inne"),
    "v2.nav.map": ("Boundary map", "Mapa granic"),
    "v2.nav.permissions": ("AI permissions", "Uprawnienia AI"),
    "v2.nav.people": ("People", "Ludzie"),
    "v2.nav.sources": ("Sources", "Źródła"),
    # ---- the "Dowód" point and panel (section 2)
    "v2.ev.point": ("Evidence for this decision ({n})", "Dowody dla tej decyzji ({n})"),
    "v2.ev.panel": ("Evidence", "Dowód"),
    "v2.ev.close": ("Close the evidence", "Zamknij dowody"),
    "v2.ev.decision": ("Decision", "Decyzja"),
    "v2.ev.basis": ("Based on", "Podstawa"),
    "v2.ev.basis.empirical": ("research", "badania"),
    "v2.ev.basis.normative": ("law and standards", "prawo i normy"),
    "v2.ev.basis.theoretical": ("theory", "teoria"),
    "v2.ev.items": ("Evidence ({n})", "Dowody ({n})"),
    "v2.ev.all_sources": ("All sources", "Wszystkie źródła"),
    "v2.ev.stance.wspiera": ("supports", "wspiera"),
    "v2.ev.stance.podwaza": ("challenges", "podważa"),
    "v2.ev.stance.niuansuje": ("nuances", "niuansuje"),
    "v2.ev.unverified": (
        "Quote not verified — summary only",
        "Cytat niezweryfikowany — tylko streszczenie",
    ),
    "v2.ev.did": ("What the researchers did", "Co zrobili badacze"),
    "v2.ev.text": ("What the text says", "Co mówi ten tekst"),
    "v2.ev.caveats": ("Limits:", "Ograniczenia:"),
    "v2.ev.means": ("What follows for Sentinel", "Co z tego wynika dla Sentinela"),
    "v2.ev.source": ("Source", "Źródło"),
    "v2.ev.new_tab": ("opens in a new tab", "otwiera się w nowej karcie"),
    "v2.ev.open_access": ("open access", "otwarty dostęp"),
    # ---- Źródła (section 2)
    "v2.src.title": ("Sources", "Źródła"),
    "v2.src.lead": (
        "Every piece of evidence behind Sentinel's decisions, for and against them. Quotes are "
        "shown only when code found them in the source.",
        "Wszystkie dowody za decyzjami Sentinela i przeciw nim. Cytat pokazujemy tylko wtedy, "
        "gdy kod znalazł go w źródle.",
    ),
    "v2.src.filters": ("Filter the sources", "Filtruj źródła"),
    "v2.src.search": ("Search", "Szukaj"),
    "v2.src.module": ("Module", "Moduł"),
    "v2.src.criterion": ("Criterion", "Kryterium"),
    "v2.src.stance": ("Stance", "Stanowisko"),
    "v2.src.kind": ("Kind", "Rodzaj"),
    "v2.src.any": ("Any", "Dowolny"),
    "v2.src.apply": ("Filter", "Filtruj"),
    "v2.src.clear": ("Clear the filters", "Wyczyść filtry"),
    "v2.src.count": ("{n} of {total} sources", "{n} z {total} źródeł"),
    "v2.src.summary_only": ("summary only", "tylko streszczenie"),
    "v2.src.used_by": ("Used by:", "Używają go:"),
    "v2.src.decision": ("decision {id}", "decyzja {id}"),
    "v2.module.projekty": ("Projects", "Projekty"),
    "v2.module.raporty": ("Reports", "Raporty"),
    "v2.module.finanse": ("Finance", "Finanse"),
    "v2.module.ludzie": ("People", "Ludzie"),
    "v2.module.uprawnienia": ("AI permissions", "Uprawnienia AI"),
    "v2.module.mapa": ("Boundary map", "Mapa granic"),
    "v2.kind.empirical": ("study with data", "badanie z danymi"),
    "v2.kind.theoretical": ("theory", "teoria"),
    "v2.kind.law": ("law", "prawo"),
    "v2.kind.standard": ("standard", "norma"),
    "v2.kind.industry": ("vendor's text", "tekst dostawcy"),
    "v2.kind.own": ("our study", "nasze badanie"),
    # ---- Mapa granic (section 3)
    "v2.map.title": ("Boundary map", "Mapa granic"),
    "v2.map.thesis": (
        "Instead of a single criterion, “AI where it saves time”, six questions decide whether AI "
        "works alone, with a person, or not at all.",
        "Zamiast jednego kryterium »AI tam, gdzie oszczędza czas« — sześć pytań decyduje, czy AI "
        "pracuje sama, z człowiekiem, czy wcale.",
    ),
    "v2.map.criteria": ("Six questions", "Sześć pytań"),
    "v2.map.normative": ("normative criterion", "kryterium normatywne"),
    "v2.map.zones": ("Zones:", "Strefy:"),
    "v2.map.table": ("Twelve company processes", "Dwanaście procesów firmy"),
    "v2.map.hint": (
        "Choose a cell for its reason and evidence, a process for where it lives in Sentinel.",
        "Wybierz komórkę, by zobaczyć powód i dowody, a proces, by zobaczyć, gdzie jest w "
        "Sentinelu.",
    ),
    "v2.map.process": ("Process", "Proces"),
    "v2.map.zone": ("Zone", "Strefa"),
    "v2.map.open": ("Open", "Otwórz"),
    "v2.map.cell": (  # the visible word first (WCAG 2.5.3)
        "{zone}: {process}, {criterion}. Show the reason and the evidence",
        "{zone}: {process}, {criterion}. Pokaż powód i dowody",
    ),
    "v2.zone.ai_samodzielnie": ("AI alone", "AI samodzielnie"),
    "v2.zone.ai_z_czlowiekiem": ("AI with a person", "AI z człowiekiem"),
    "v2.zone.tylko_czlowiek": ("only a person", "tylko człowiek"),
    "v2.zone.short.ai_samodzielnie": ("AI alone", "sama AI"),
    "v2.zone.short.ai_z_czlowiekiem": ("with a person", "z człowiekiem"),
    "v2.zone.short.tylko_czlowiek": ("person only", "człowiek"),
    # ---- Uprawnienia AI (section 4)
    "v2.perm.title": ("AI permissions", "Uprawnienia AI"),
    "v2.perm.lead": (
        "The language model in Sentinel works on text and nothing else. Everything it returns is "
        "checked by code, and every change waits for you.",
        "Model językowy w Sentinelu pracuje na tekście i na niczym więcej. Wszystko, co zwraca, "
        "sprawdza kod, a każda zmiana czeka na Ciebie.",
    ),
    "v2.perm.may": ("What AI may do", "Co AI może"),
    "v2.perm.may_not": ("What AI may not do", "Czego AI nie może"),
    "v2.perm.may.read": (
        "Read the text you give it: a message, a report, a project description.",
        "Czytać tekst, który mu dajesz: wiadomość, raport, opis projektu.",
    ),
    "v2.perm.may.format": (
        "Return data in a fixed format, which code checks against a schema.",
        "Zwracać dane w stałym formacie, który kod sprawdza według schematu.",
    ),
    "v2.perm.not.save": ("Save anything", "Zapisać czegokolwiek"),
    "v2.perm.not.send": ("Send anything to anyone", "Wysłać czegokolwiek do kogokolwiek"),
    "v2.perm.not.approve": ("Approve a change", "Zatwierdzić zmiany"),
    "v2.perm.not.compute": (
        "Compute a number you see (chance, date, budget)",
        "Policzyć liczby, którą widzisz (szansa, data, budżet)",
    ),
    "v2.perm.not.choose": ("Choose an action", "Wybrać działania"),
    "v2.perm.not.connect": (
        "Connect to anything: no tools, no internet, no other systems",
        "Połączyć się z czymkolwiek: bez narzędzi, internetu i innych systemów",
    ),
    "v2.perm.not.projects": (
        "See other projects or other people's data",
        "Zobaczyć innych projektów ani cudzych danych",
    ),
    "v2.perm.now": ("Now", "Teraz"),
    "v2.perm.model.cloud": (
        "Model in the cloud: {model} through {provider}.",
        "Model w chmurze: {model} przez {provider}.",
    ),
    "v2.perm.model.local": (
        "Local model on this server: {model}.",
        "Model lokalny na tym serwerze: {model}.",
    ),
    "v2.perm.model.none": ("AI is switched off.", "AI jest wyłączone."),
    "v2.perm.leaves.cloud": (
        "The text of a message goes to the provider: {provider}.",
        "Tekst wiadomości trafia do dostawcy: {provider}.",
    ),
    "v2.perm.leaves.local": (
        "Nothing leaves this server.",
        "Nic nie wychodzi poza ten serwer.",
    ),
    "v2.perm.leaves.none": (
        "Nothing goes to any model.",
        "Nic nie trafia do żadnego modelu.",
    ),
    "v2.perm.leaves.voice": (
        "Recordings go to Groq for speech recognition and are not kept.",
        "Nagrania trafiają do Groq do rozpoznania mowy i nie są przechowywane.",
    ),
    "v2.perm.calls": ("Latest calls of the model", "Ostatnie wywołania modelu"),
    "v2.perm.calls.none": (
        "No calls since the server started.",
        "Brak wywołań od uruchomienia serwera.",
    ),
    "v2.perm.calls.note": (
        "Only when, what for, where and how long: never the content. The list lives in memory "
        "and disappears when the server restarts.",
        "Tylko kiedy, po co, dokąd i jak długo: nigdy treść. Lista jest w pamięci i znika po "
        "ponownym uruchomieniu serwera.",
    ),
    "v2.perm.col.time": ("Time", "Godzina"),
    "v2.perm.col.role": ("What for", "Po co"),
    "v2.perm.col.provider": ("Where", "Dokąd"),
    "v2.perm.col.chars": ("Length (characters)", "Długość (znaki)"),
    "v2.perm.col.seconds": ("Duration", "Czas"),
    "v2.perm.cached": ("from memory", "z pamięci"),
    "v2.perm.role.extract": ("Description into tasks", "Opis w zadania"),
    "v2.perm.role.propose": ("Proposed actions", "Propozycje działań"),
    "v2.perm.role.explain": ("Explanation of a decision", "Wyjaśnienie decyzji"),
    "v2.perm.role.read": ("Message into data", "Wiadomość w dane"),
    "v2.perm.role.test": ("Connection test", "Test połączenia"),
    "v2.perm.role.attack": ("Attack test", "Próba ataku"),
    "v2.perm.attack": ("Attack test", "Próba ataku"),
    "v2.perm.attack.lead": (
        "A status message with a hidden instruction goes through the same path as any message "
        "from your team. See what the model returns and what Sentinel does with it.",
        "Wiadomość o postępie z ukrytym poleceniem przechodzi tę samą drogę co każda wiadomość "
        "od zespołu. Zobacz, co zwraca model i co robi z tym Sentinel.",
    ),
    "v2.perm.attack.sample": ("The message", "Wiadomość"),
    "v2.perm.attack.mode": ("How to run it", "Jak uruchomić"),
    "v2.perm.attack.replay": ("Recorded answer of the model", "Nagrana odpowiedź modelu"),
    "v2.perm.attack.live_option": ("Live", "Na żywo"),
    "v2.perm.attack.no_ai": ("AI is switched off", "AI jest wyłączone"),
    "v2.perm.attack.capped": ("counts towards today's limit", "wlicza się do dzisiejszego limitu"),
    "v2.perm.attack.run": ("Run", "Uruchom"),
    "v2.perm.attack.working": ("The model is reading…", "Model czyta…"),
    "v2.perm.attack.recorded": (
        "Recorded answer of {model} ({provider}) from {date}.",
        "Nagrana odpowiedź {model} ({provider}) z {date}.",
    ),
    "v2.perm.attack.live": ("Live answer of {model}.", "Odpowiedź {model} na żywo."),
    "v2.perm.attack.ignored": (
        "The instruction was ignored: the model marked that sentence as not understood.",
        "Polecenie zostało zignorowane: model oznaczył to zdanie jako nierozpoznane.",
    ),
    "v2.perm.attack.carded": (
        "The model turned the sentence into an item to confirm; the format has no field that "
        "could approve anything.",
        "Model zamienił to zdanie w pozycję do potwierdzenia; format nie ma pola, które mogłoby "
        "cokolwiek zatwierdzić.",
    ),
    "v2.perm.attack.rejected": (
        "The schema rejected the model's answer: nothing reached the project.",
        "Schemat odrzucił odpowiedź modelu: nic nie trafiło do projektu.",
    ),
    "v2.perm.attack.no_function": (
        "Sentinel has no function through which AI could do this.",
        "Sentinel nie ma funkcji, którą AI mogłoby to zrobić.",
    ),
    "v2.perm.attack.review": (
        "To confirm (a report of {date})",
        "Do potwierdzenia (raport z {date})",
    ),
    "v2.perm.attack.nothing": ("Nothing to confirm.", "Nic do potwierdzenia."),
    "v2.perm.attack.answer": ("What the model returned", "Co zwrócił model"),
    "v2.perm.attack.saved": (
        "Nothing was saved: no report, no decision, no copy of the answer.",
        "Nic nie zapisano: żadnego raportu, decyzji ani kopii odpowiedzi.",
    ),
    "v2.perm.error.limit": (
        "Today's limit of AI requests has been reached. Try the recorded answer.",
        "Dzisiejszy limit zapytań do AI się wyczerpał. Spróbuj nagranej odpowiedzi.",
    ),
    "v2.perm.error.unavailable": (
        "AI is switched off on this server. Try the recorded answer.",
        "AI jest wyłączone na tym serwerze. Spróbuj nagranej odpowiedzi.",
    ),
    "v2.perm.error.failed": (
        "The model did not answer. Try again or use the recorded answer.",
        "Model nie odpowiedział. Spróbuj ponownie albo użyj nagranej odpowiedzi.",
    ),
    # ---- "Twoja ocena" (section 6)
    "v2.own.title": ("What would you do?", "Co byś zrobił?"),
    "v2.own.hint": (
        "Choose first, then see what Sentinel recommends and why.",
        "Najpierw wybierz własną odpowiedź, potem zobaczysz, co proponuje Sentinel i dlaczego.",
    ),
    "v2.own.context": (
        "Without changes the chance of meeting the deadline is {n} in 100.",
        "Bez zmian szansa na termin wynosi {n} na 100.",
    ),
    "v2.own.skip": ("Show it now", "Pokaż od razu"),
    "v2.own.line": (
        "Your choice: {mine} · Sentinel: {sentinel}",
        "Twój wybór: {mine} · Sentinel: {sentinel}",
    ),
    "v2.own.agree.one": (
        "You agree with Sentinel in {agreed} of {n} decision",
        "Zgadzasz się z Sentinelem w {agreed} z {n} decyzji",
    ),
    "v2.own.agree.few": (
        "You agree with Sentinel in {agreed} of {n} decisions",
        "Zgadzasz się z Sentinelem w {agreed} z {n} decyzji",
    ),
    "v2.own.agree.many": (
        "You agree with Sentinel in {agreed} of {n} decisions",
        "Zgadzasz się z Sentinelem w {agreed} z {n} decyzji",
    ),
    "v2.psettings.assessment": ("My assessment first", "Najpierw moja ocena"),
    "v2.psettings.assessment_hint": (
        "Before Sentinel shows a recommendation, you choose what you would do. Thinking first "
        "lowers blind trust in AI, though many find it tiresome: you can always skip it.",
        "Zanim Sentinel pokaże rekomendację, wybierasz własne działanie. Namysł zmniejsza "
        "ślepe zaufanie do AI, choć wielu osobom przeszkadza: zawsze możesz go pominąć.",
    ),
    "v2.psettings.assessment_save": ("Save", "Zapisz"),
    "v2.psettings.saved.assessment": ("Saved.", "Zapisano."),
    # ---- Ludzie (section 5)
    "v2.people.title": ("People", "Ludzie"),
    "v2.people.absent": ("What is not here, on purpose", "Czego tu celowo nie ma"),
    "v2.people.absent.performance": ("Performance scores", "Ocena wydajności"),
    "v2.people.absent.ranking": (
        "Ranking of people for substitutions",
        "Ranking ludzi do zastępstw",
    ),
    "v2.people.absent.mood": ("Mood and emotion analysis", "Analiza nastroju i emocji"),
    "v2.people.absent.reasons": ("Reasons for absence", "Powody nieobecności"),
    "v2.people.why.performance": (
        "Rating workers with AI is high risk under the AI Act, and a score that becomes a target "
        "stops telling the truth.",
        "Ocena pracowników przez AI to według AI Act wysokie ryzyko, a wskaźnik, który staje się "
        "celem, przestaje mówić prawdę.",
    ),
    "v2.people.why.ranking": (
        "A substitution is a decision about tasks and availability; whom to ask is your choice.",
        "Zastępstwo to decyzja o zadaniach i dostępności; kogo poprosić, wybierasz Ty.",
    ),
    "v2.people.why.mood": (
        "Inferring emotions at work is prohibited by the AI Act; the model's format has no field "
        "for it.",
        "AI Act zakazuje wnioskowania o emocjach w pracy; format odpowiedzi modelu nie ma na to "
        "pola.",
    ),
    "v2.people.why.reasons": (
        "A reason often reveals health; Sentinel stores only when someone is away.",
        "Powód często ujawnia stan zdrowia; Sentinel zapisuje tylko, kiedy kogoś nie ma.",
    ),
    "v2.people.load": (
        "Workload in the next two weeks",
        "Obciążenie w najbliższych dwóch tygodniach",
    ),
    "v2.people.principle": (
        "Sentinel plans by roles and availability; it does not rate people.",
        "Sentinel planuje według ról i dostępności, nie ocenia ludzi.",
    ),
    "v2.people.period": ("{first} – {last}", "{first} – {last}"),
    "v2.people.col.role": ("Role", "Rola"),
    "v2.people.col.load": ("Workload", "Obciążenie"),
    "v2.people.away_all": ("absent the whole period", "nieobecność przez cały okres"),
    "v2.people.none": (
        "No project with a plan yet.",
        "Nie ma jeszcze projektu z planem.",
    ),
}
