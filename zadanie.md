Etap 3 – Implementacja Modelu 
i
Etap 4 – Implementacja Procesu ETL

Podstawowe informacje
Finalny termin oddania etapów 3 i 4 to 8/10 czerwca (w zależności od terminu Waszych zajęć). Możecie przygotować jeden wspólny raport lub dwa osobne - według własnych preferencji.
Nie ma obowiązku wgrywania pracy 24 godziny przed zajęciami. Możecie ją przesłać tuż przed zajęciami lub nawet w ich trakcie (ale nie po zajęciach).
Zajęcia w dniach 1 i 3 czerwca są obowiązkowe. Na tych zajęciach należy obowiązkowo pokazać postęp prac. Możecie oddać etap 3, ale nie jest to wymagane - ważne jest przede wszystkim pokazanie realnego postępu względem poprzednich zajęć, bo może np. wolicie rozpocząć od procesu czyszczenia danych.
Postęp prezentowany 1 i 3 czerwca nie będzie oceniany i nie należy nic wgrywać na e-portal. Wyjątkiem jest sytuacja, w której zdecydujecie się oddać etap 3 - wtedy zostanie on oceniony po zajęciach.
Etapy 3 i 4 będą oceniane osobno. Oznacza to, że za etap 3 można otrzymać 0–10 punktów oraz za etap 4 również 0–10 punktów.
Jeśli macie jakiekolwiek pytania lub coś jest niejasne, piszcie maila, pytajcie na zajęciach albo przyjdźcie na konsultacje w poniedziałek (proszę wcześniej dać znać).

Finalny plan procesu 
Podstawą do realizacji etapu jest właściwe uporządkowanie celu procesu, występujących problemów z danymi (tzw. anomalii), i opracowanie planu procesu przygotowania modelu danych (czyszczenie, uzgadnianie, wzbogacanie danych).
Na podstawie przygotowanego w poprzednim etapie wstępnego planu projektu zdefiniujcie: 
	•	Jakie konkretnie macie  problemy z surowymi danymi? (np. braki w adresach, różne formaty dat, literówki w nazwach klientów) i jak zamierzacie je naprawić? (np. usuwanie spacji, ujednolicanie wielkości liter, pobieranie brakujących danych z innego systemu).

	•	Dla każdej tabeli wymiarów (np. Klienci, Produkty, Sklepy) oraz każdej tabeli faktów (np. Sprzedaż, Zamówienia) musicie przygotować metryczkę, która zawiera:

	•	Źródło: Skąd bierzecie te dane? (np. tabela customers z bazy CRM, plik stores.csv).
	•	Transformacje: Co dokładnie z nimi robicie po drodze? (np. „Łączymy Imię i Nazwisko w jedną kolumnę”, „Zmieniamy format daty na YYYY-MM-DD”, „Wyliczamy wiek na podstawie daty urodzenia”).
	•	Kontrola Jakości Danych: Zdefiniujcie „punkty kontrolne”, aby uniknąć zasady garbage in, garbage out. Dla każdej tabeli określcie: Jakie warunki (oczekiwania) muszą spełniać dane? Co się dzieje, gdy dane są nieprawidłowe (nie spełniają warunku)? (np. czy odrzucacie rekord do osobnej tabeli błędów, podmieniacie wartość na domyślną?).
	•	Weryfikacja (Testy): Jak sprawdzicie, że proces zadziałał dobrze? (np. „Upewnimy się, że kolumna z ceną nie ma wartości pustych (NULL)”).

	•	Oprócz opisu tekstowego macie narysować diagram, który finalnie pokaże przepływ: od źródeł, przez warstwę czyszczenia aż do gotowych tabel Wymiarów i Faktów.

Implementacja ETL
Waszym zadaniem w tych etapach jest fizyczne zbudowanie modelu oraz przygotowanie danych, które pozwolą na sprawną analizę biznesową i pomogą w podejmowaniu trafnych decyzji. Zadanie możecie zrealizować na jednym z dwóch poziomów trudności, od których zależy Wasza punktacja końcowa (etapu 3 i 4):

Wersja podstawowa ( max 5pkt. lub 6pkt.)
	•	Narzędzia: SQL Server (do przechowywania danych) oraz Power BI Desktop (do pobierania, przekształcania i modelowania danych).
	•	Co musicie zrobić: Opracować poprawny model semantyczny (z hierarchiami i grupowaniem) oraz przygotować odpowiednie agregacje danych.
	•	Jak podwyższyć punktację (max 6pkt.): Wprowadzić dodatkowe miary obliczeniowe przy użyciu języka DAX.

Wersja rozszerzona (od 6.5pkt. do 10pkt.)
Zakres prac jest taki sam jak w wersji podstawowej, ale technologia jest inna.
	•	Narzędzia: Pandas, SQL, Airflow, Luigi czy SQL Server Integration Services (SSIS).
	•	Co musicie zrobić: Przygotować dane w postaci schematu gwiazdy za pomocą powyższych narzędzi. Następnie musicie zaimplementować wielowymiarową bazę danych (jako kostkę MOLAP w SQL Server Analysis Services lub w modelu kolumnowym ROLAP).

Jeżeli wybierzecie wersję podstawą, to za etap 3 możecie dostać od 0pkt. do max 6pkt.
Jeżeli wybierzecie wersję podstawą, to za etap 4 możecie dostać od 0pkt. do max 6pkt.

Jeżeli wybierzecie wersję rozszerzoną, to za etap 3 możecie dostać od 6.5pkt. do max 10pkt.
Jeżeli wybierzecie wersję rozszerzoną, to za etap 4 możecie dostać od 6.5pkt. do max 10pkt.

Zakres w wersji podstawowej (Proces ETL)
1. Pobieranie danych (Ekstrakcja) : 
W tym kroku pozyskujecie informacje z systemów źródłowych. Waszym zadaniem jest: 
	•	Określić sposób (tryb) dostępu do danych. 
	•	Wykrywać błędy i anomalie już na etapie pobierania. 
	•	Identyfikować i odpowiednio obsługiwać zmiany w danych.
Wdróżcie ekstrakcję przyrostową (czyli pobierajcie tylko nowe lub zmienione dane, zamiast przeładowywać za każdym razem całość).

2. Przetwarzanie i porządkowanie danych (Transformacja)
Wszystkie prace w tym kroku musicie realizować w wydzielonym, technicznym obszarze roboczym (tzw. obszar staging). Wymagane działania to: 
	•	Oczyszczanie: Usuwajcie anomalie, a także uzgadniajcie i standaryzujcie dane.
	•	Wymiar Czasu: Stwórzcie stały/statyczny wymiar czasu (tzw. kalendarz). Obejmuje to ujednolicenie nazw, zdefiniowanie reguł użycia, zbudowanie hierarchii (np. rok > kwartał > miesiąc) oraz dodanie kolumn obliczeniowych.
	•	Pozostałe Wymiary: Zbudujcie inne wymiary biznesowe (tutaj również pamiętajcie o standaryzacji nazw i utworzeniu odpowiednich kolumn obliczeniowych).
	•	Fakty i Miary: Zaimplementujcie tabelę faktów oraz określcie podstawowe miary.

3. Ładowanie i modelowanie danych
Gotowe dane przenieście do wybranej bazy danych lub narzędzia analitycznego (np. Power BI Desktop) w tym, budując wielowymiarowy model w architekturze ROLAP. Wasze zadania w tym kroku:
	•	Mechanizmy analityczne: Utwórzcie agregaty oraz zdefiniujcie dodatkowe miary obliczeniowe (wykorzystując do tego język DAX).
	•	Bezpieczeństwo: Zaimplementujcie role użytkowników, aby zarządzać uprawnieniami.
	•	Ciągłość aktualizacji: Zadbajcie o to, by Wasze rozwiązanie obsługiwało iteracyjny (ciągły) napływ informacji. Oznacza to, że system musi sprawnie funkcjonować z zestawem danych, który został uaktualniony o nowe zdarzenia i transakcje zrealizowane po poprzednim ładowaniu.

4. Kontrola jakości: Na sam koniec wdróżcie mechanizmy, które w sposób automatyczny będą weryfikować, czy załadowane przez Was dane są w pełni kompletne i poprawne.

Każdy krok (1,2,3,4) musi zostać podsumowany w prezentacji/raporcie.

Implementacja modelu
Głównym celem tego etapu jest fizyczna implementacja wcześniej zaprojektowanego modelu danych. W raporcie należy przedstawić oraz podsumować, w jaki sposób został zrealizowany wielowymiarowy model danych w praktyce, np. poprzez implementację schematu gwiazdy.
W prezentacji/raporcie powinny znaleźć się: graficzna reprezentacja bazy danych przedstawiająca zastosowany model (np. schemat gwiazdy) oraz opis, podsumowanie.

Powodzenia!
