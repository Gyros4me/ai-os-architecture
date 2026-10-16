"""
Extended books dataset: 45 books with trilogies and rich descriptions
"""
import json
from typing import List, Dict


def generate_sample_books() -> List[Dict]:
    """
    Generate extended sample books dataset (45 books)
    Includes trilogies and detailed descriptions for semantic search
    """
    books = [
        # Harry Potter Series
        {
            "id": "1",
            "title": "Harry Potter e la Pietra Filosofale",
            "authors": ["J.K. Rowling"],
            "isbn": "0439554934",
            "language_code": "ita",
            "num_pages": 309,
            "ratings_count": 8868544,
            "average_rating": 4.47,
            "publication_date": "1997",
            "publisher": "Salani",
            "description": "Un giovane mago scopre il suo destino magico. Fantasy, avventura, magia, scuola di magia"
        },
        {
            "id": "2",
            "title": "Harry Potter e la Camera dei Segreti",
            "authors": ["J.K. Rowling"],
            "isbn": "0439554896",
            "language_code": "ita",
            "num_pages": 341,
            "ratings_count": 7659000,
            "average_rating": 4.43,
            "publication_date": "1998",
            "publisher": "Salani",
            "description": "Il secondo anno a Hogwarts porta nuovi misteri e pericoli. Avventura magica, serpenti, magia oscura"
        },
        
        # Murakami Collection
        {
            "id": "3",
            "title": "1Q84",
            "authors": ["Haruki Murakami"],
            "isbn": "0307593312",
            "language_code": "eng",
            "num_pages": 925,
            "ratings_count": 245621,
            "average_rating": 3.93,
            "publication_date": "2009",
            "publisher": "Knopf",
            "description": "Una realtÃ  alternativa nel 1984. Storia surreale, mondi paralleli, amore impossibile"
        },
        {
            "id": "4",
            "title": "Norwegian Wood",
            "authors": ["Haruki Murakami"],
            "isbn": "0375704027",
            "language_code": "eng",
            "num_pages": 296,
            "ratings_count": 478392,
            "average_rating": 4.00,
            "publication_date": "1987",
            "publisher": "Vintage",
            "description": "Una storia d'amore nostalgica e malinconica. GioventÃ¹, perdita, memoria, tristezza, solitudine"
        },
        {
            "id": "5",
            "title": "Kafka sulla Spiaggia",
            "authors": ["Haruki Murakami"],
            "isbn": "1400079276",
            "language_code": "eng",
            "num_pages": 505,
            "ratings_count": 298456,
            "average_rating": 4.13,
            "publication_date": "2002",
            "publisher": "Vintage",
            "description": "Due storie parallele surreali e misteriose. Viaggio interiore, destino, ricerca di sÃ©"
        },
        
        # Italian Classics
        {
            "id": "6",
            "title": "Il Nome della Rosa",
            "authors": ["Umberto Eco"],
            "isbn": "0156001314",
            "language_code": "ita",
            "num_pages": 536,
            "ratings_count": 234156,
            "average_rating": 4.13,
            "publication_date": "1980",
            "publisher": "Bompiani",
            "description": "Mistero medievale in un'abbazia. Thriller storico, indagine, omicidi, filosofia"
        },
        {
            "id": "7",
            "title": "Oceano Mare",
            "authors": ["Alessandro Baricco"],
            "isbn": "8817115606",
            "language_code": "ita",
            "num_pages": 208,
            "ratings_count": 89234,
            "average_rating": 4.05,
            "publication_date": "1993",
            "publisher": "Rizzoli",
            "description": "Storie intrecciate sulla costa dell'oceano. Poesia, mare, destini incrociati"
        },
        
        # Latin American Literature
        {
            "id": "8",
            "title": "Cent'anni di solitudine",
            "authors": ["Gabriel Garci­a Marquez"],
            "isbn": "0060883286",
            "language_code": "spa",
            "num_pages": 417,
            "ratings_count": 678912,
            "average_rating": 4.11,
            "publication_date": "1967",
            "publisher": "Mondadori",
            "description": "La saga della famiglia BuendÃ­a attraverso generazioni. Solitudine, tristezza, realismo magico, destino tragico, melanconia"
        },
        
        # Hemingway
        {
            "id": "9",
            "title": "Il Sole Splende Ancora",
            "authors": ["Ernest Hemingway"],
            "isbn": "0684800713",
            "language_code": "eng",
            "num_pages": 251,
            "ratings_count": 345678,
            "average_rating": 3.83,
            "publication_date": "1926",
            "publisher": "Scribner",
            "description": "Expatriati americani in Europa dopo la guerra. Generazione perduta, amore, disillusione"
        },
        
        # Tolkien - Lord of the Rings
        {
            "id": "10",
            "title": "Il Signore degli Anelli - La Compagnia dell'Anello",
            "authors": ["J.R.R. Tolkien"],
            "isbn": "0618346252",
            "language_code": "ita",
            "num_pages": 423,
            "ratings_count": 2456789,
            "average_rating": 4.36,
            "publication_date": "1954",
            "publisher": "Bompiani",
            "description": "L'inizio del viaggio epico per distruggere l'anello. Fantasy, avventura, magia, eroi"
        },
        {
            "id": "11",
            "title": "Il Signore degli Anelli - Le Due Torri",
            "authors": ["J.R.R. Tolkien"],
            "isbn": "0618346260",
            "language_code": "ita",
            "num_pages": 352,
            "ratings_count": 2123456,
            "average_rating": 4.45,
            "publication_date": "1954",
            "publisher": "Bompiani",
            "description": "Il secondo volume della trilogia. Battaglie epiche, guerra, coraggio, sacrificio"
        },
        {
            "id": "12",
            "title": "Il Signore degli Anelli - Il Ritorno del Re",
            "authors": ["J.R.R. Tolkien"],
            "isbn": "0618346279",
            "language_code": "ita",
            "num_pages": 416,
            "ratings_count": 1987654,
            "average_rating": 4.52,
            "publication_date": "1955",
            "publisher": "Bompiani",
            "description": "La conclusione epica della saga. Battaglia finale, vittoria, ritorno a casa, speranza"
        },
        
        # Jane Austen
        {
            "id": "13",
            "title": "Orgoglio e Pregiudizio",
            "authors": ["Jane Austen"],
            "isbn": "0141439513",
            "language_code": "eng",
            "num_pages": 432,
            "ratings_count": 3456789,
            "average_rating": 4.27,
            "publication_date": "1813",
            "publisher": "Penguin",
            "description": "Romanzo classico sull'amore e la societÃ . Storia d'amore, romantico, commedia, matrimonio"
        },
        
        # Dan Brown
        {
            "id": "14",
            "title": "Il Codice da Vinci",
            "authors": ["Dan Brown"],
            "isbn": "0307474275",
            "language_code": "ita",
            "num_pages": 689,
            "ratings_count": 2789456,
            "average_rating": 3.88,
            "publication_date": "2003",
            "publisher": "Mondadori",
            "description": "Thriller d'azione mozzafiato con simboli e misteri religiosi. Robert Langdon corre contro il tempo in una caccia adrenalinica piena di suspense, enigmi intricati, cospirazione internazionale, indagine frenetica, azione esplosiva, inseguimenti pericolosi"
        },
        
        # Contemporary Fiction
        {
            "id": "15",
            "title": "La Spiaggia",
            "authors": ["Alex Garland"],
            "isbn": "1573226521",
            "language_code": "eng",
            "num_pages": 436,
            "ratings_count": 234567,
            "average_rating": 3.68,
            "publication_date": "1996",
            "publisher": "Riverhead",
            "description": "Avventura su un'isola paradisiaca che diventa incubo. Giovani, viaggio, pericolo"
        },
        
        # Paulo Coelho
        {
            "id": "16",
            "title": "L'Alchimista",
            "authors": ["Paulo Coelho"],
            "isbn": "0062315005",
            "language_code": "por",
            "num_pages": 208,
            "ratings_count": 1234567,
            "average_rating": 3.90,
            "publication_date": "1988",
            "publisher": "Bompiani",
            "description": "Un pastore alla ricerca del suo destino. Viaggio spirituale, sogni, crescita personale"
        },
        
        # Trilogia dello Spazio delle Varianti - Vadim Zeland
        {
            "id": "17",
            "title": "Lo Spazio delle Varianti",
            "authors": ["Vadim Zeland"],
            "isbn": "8897399010",
            "language_code": "ita",
            "num_pages": 304,
            "ratings_count": 45678,
            "average_rating": 4.15,
            "publication_date": "2005",
            "publisher": "Macro Edizioni",
            "description": "Primo volume sul Reality Transurfing. RealtÃ  alternative, destino, scelte, energia"
        },
        {
            "id": "18",
            "title": "Il Fruscio delle Stelle del Mattino",
            "authors": ["Vadim Zeland"],
            "isbn": "8897399029",
            "language_code": "ita",
            "num_pages": 288,
            "ratings_count": 38901,
            "average_rating": 4.12,
            "publication_date": "2006",
            "publisher": "Macro Edizioni",
            "description": "Secondo volume della trilogia Transurfing. Manifestazione, intenzione, realtÃ  parallele"
        },
        {
            "id": "19",
            "title": "Avanti nel Passato",
            "authors": ["Vadim Zeland"],
            "isbn": "8897399037",
            "language_code": "ita",
            "num_pages": 272,
            "ratings_count": 35234,
            "average_rating": 4.08,
            "publication_date": "2007",
            "publisher": "Macro Edizioni",
            "description": "Terzo volume conclusivo. Tempo, pendoli, libertÃ  di scelta, consapevolezza"
        },
        
        # Millennium Trilogy - Stieg Larsson
        {
            "id": "20",
            "title": "Uomini che Odiano le Donne",
            "authors": ["Stieg Larsson"],
            "isbn": "8838921679",
            "language_code": "swe",
            "num_pages": 576,
            "ratings_count": 1567890,
            "average_rating": 4.14,
            "publication_date": "2005",
            "publisher": "Marsilio",
            "description": "Thriller scandinavo con hacker e giornalista. Mistero, indagine, crimine, tecnologia"
        },
        {
            "id": "21",
            "title": "La Ragazza che Giocava con il Fuoco",
            "authors": ["Stieg Larsson"],
            "isbn": "8838922187",
            "language_code": "swe",
            "num_pages": 672,
            "ratings_count": 1234567,
            "average_rating": 4.08,
            "publication_date": "2006",
            "publisher": "Marsilio",
            "description": "Secondo capitolo della saga Millennium. Vendetta, hacking, cospirazione"
        },
        {
            "id": "22",
            "title": "La Regina dei Castelli di Carta",
            "authors": ["Stieg Larsson"],
            "isbn": "8838922519",
            "language_code": "swe",
            "num_pages": 720,
            "ratings_count": 1098765,
            "average_rating": 4.05,
            "publication_date": "2007",
            "publisher": "Marsilio",
            "description": "Conclusione della trilogia Millennium. Giustizia, veritÃ , finale epico"
        },
        
        # Science Fiction Classics
        {
            "id": "23",
            "title": "1984",
            "authors": ["George Orwell"],
            "isbn": "0451524934",
            "language_code": "eng",
            "num_pages": 328,
            "ratings_count": 3456789,
            "average_rating": 4.19,
            "publication_date": "1949",
            "publisher": "Mondadori",
            "description": "Distopia totalitaria sul controllo sociale. Futuro oscuro, sorveglianza, oppressione, libertÃ "
        },
        {
            "id": "24",
            "title": "Il Mondo Nuovo",
            "authors": ["Aldous Huxley"],
            "isbn": "0060850523",
            "language_code": "eng",
            "num_pages": 288,
            "ratings_count": 1876543,
            "average_rating": 3.99,
            "publication_date": "1932",
            "publisher": "Mondadori",
            "description": "SocietÃ  futura controllata dalla tecnologia. Fantascienza, distopia, controllo, felicitÃ  forzata"
        },
        
        # Horror/Thriller
        {
            "id": "25",
            "title": "Shining",
            "authors": ["Stephen King"],
            "isbn": "0307743659",
            "language_code": "eng",
            "num_pages": 447,
            "ratings_count": 987654,
            "average_rating": 4.23,
            "publication_date": "1977",
            "publisher": "Sperling & Kupfer",
            "description": "Horror psicologico in un hotel isolato. Paura, follia, terrore, fantasmi, isolamento"
        },
        {
            "id": "26",
            "title": "It",
            "authors": ["Stephen King"],
            "isbn": "0670813028",
            "language_code": "eng",
            "num_pages": 1138,
            "ratings_count": 1345678,
            "average_rating": 4.25,
            "publication_date": "1986",
            "publisher": "Sperling & Kupfer",
            "description": "Terrore di un mostro che si nutre di paura. Horror, paura, amicizia, infanzia"
        },
        
        # Italian Contemporary
        {
            "id": "27",
            "title": "La Solitudine dei Numeri Primi",
            "authors": ["Paolo Giordano"],
            "isbn": "8804589361",
            "language_code": "ita",
            "num_pages": 304,
            "ratings_count": 234567,
            "average_rating": 3.87,
            "publication_date": "2008",
            "publisher": "Mondadori",
            "description": "Due anime ferite che si cercano. Solitudine, tristezza, amore impossibile, dolore"
        },
        {
            "id": "28",
            "title": "Gomorra",
            "authors": ["Roberto Saviano"],
            "isbn": "8804566507",
            "language_code": "ita",
            "num_pages": 352,
            "ratings_count": 345678,
            "average_rating": 4.01,
            "publication_date": "2006",
            "publisher": "Mondadori",
            "description": "Inchiesta sulla camorra napoletana. Crimine, mafia, veritÃ , coraggio"
        },
        
        # Romance/Love Stories
        {
            "id": "29",
            "title": "Io Prima di Te",
            "authors": ["Jojo Moyes"],
            "isbn": "8804642475",
            "language_code": "eng",
            "num_pages": 416,
            "ratings_count": 876543,
            "average_rating": 4.28,
            "publication_date": "2012",
            "publisher": "Mondadori",
            "description": "Storia d'amore commovente e profondamente tragica. Una relazione impossibile che trasforma due vite. Amore struggente, perdita devastante, scelte difficili strazianti, emozioni intense lacrimanti, dolore profondo, sacrificio d'amore, tenerezza infinita"
        },
        {
            "id": "30",
            "title": "Le Pagine della Nostra Vita",
            "authors": ["Nicholas Sparks"],
            "isbn": "0446605239",
            "language_code": "eng",
            "num_pages": 214,
            "ratings_count": 765432,
            "average_rating": 4.07,
            "publication_date": "1996",
            "publisher": "Sperling & Kupfer",
            "description": "Romanzo d'amore attraverso i decenni. Amore eterno, memoria, fedeltÃ , romantico"
        },
        
        # Philosophy/Essays
        {
            "id": "31",
            "title": "Siddharta",
            "authors": ["Hermann Hesse"],
            "isbn": "0553208845",
            "language_code": "ger",
            "num_pages": 152,
            "ratings_count": 654321,
            "average_rating": 4.08,
            "publication_date": "1922",
            "publisher": "Adelphi",
            "description": "Viaggio spirituale alla ricerca dell'illuminazione. Saggezza, meditazione, crescita interiore"
        },
        
        # Adventure/Travel
        {
            "id": "32",
            "title": "Sulla Strada",
            "authors": ["Jack Kerouac"],
            "isbn": "0142437255",
            "language_code": "eng",
            "num_pages": 293,
            "ratings_count": 543210,
            "average_rating": 3.71,
            "publication_date": "1957",
            "publisher": "Mondadori",
            "description": "Viaggio attraverso l'America. LibertÃ , avventura, giovinezza, scoperta"
        },
        {
            "id": "33",
            "title": "Into the Wild - Nelle Terre Estreme",
            "authors": ["Jon Krakauer"],
            "isbn": "0385486804",
            "language_code": "eng",
            "num_pages": 207,
            "ratings_count": 432109,
            "average_rating": 3.99,
            "publication_date": "1996",
            "publisher": "Feltrinelli",
            "description": "Storia vera di un giovane nell'Alaska selvaggia. Avventura, natura, solitudine, libertÃ "
        },
        
        # Historical Fiction
        {
            "id": "34",
            "title": "I Pilastri della Terra",
            "authors": ["Ken Follett"],
            "isbn": "0451166892",
            "language_code": "eng",
            "num_pages": 976,
            "ratings_count": 987654,
            "average_rating": 4.33,
            "publication_date": "1989",
            "publisher": "Mondadori",
            "description": "Epica medievale sulla costruzione di una cattedrale. Storia, medioevo, passione, potere"
        },
        
        # Mystery/Detective
        {
            "id": "35",
            "title": "Il Silenzio degli Innocenti",
            "authors": ["Thomas Harris"],
            "isbn": "0312924585",
            "language_code": "eng",
            "num_pages": 338,
            "ratings_count": 876543,
            "average_rating": 4.09,
            "publication_date": "1988",
            "publisher": "Mondadori",
            "description": "Thriller psicologico con serial killer. Paura, suspense, indagine, psicologia"
        },
        
        # Young Adult
        {
            "id": "36",
            "title": "Hunger Games",
            "authors": ["Suzanne Collins"],
            "isbn": "0439023483",
            "language_code": "eng",
            "num_pages": 374,
            "ratings_count": 6789012,
            "average_rating": 4.32,
            "publication_date": "2008",
            "publisher": "Mondadori",
            "description": "Distopia action-packed con giochi mortali televisivi. Katniss combatte per la sopravvivenza in un'arena letale. Avventura survival estrema, azione brutale, combattimenti violenti, tensione costante, coraggio eroico, ribellione giovanile, sacrificio nobile"
        },
        {
            "id": "37",
            "title": "Divergent",
            "authors": ["Veronica Roth"],
            "isbn": "0062024027",
            "language_code": "eng",
            "num_pages": 487,
            "ratings_count": 3456789,
            "average_rating": 4.15,
            "publication_date": "2011",
            "publisher": "De Agostini",
            "description": "SocietÃ  divisa in fazioni. Scelta, identitÃ , coraggio, adolescenti"
        },
        
        # Poetry/Short Stories
        {
            "id": "38",
            "title": "Venti Poesie d'Amore e una Canzone Disperata",
            "authors": ["Pablo Neruda"],
            "isbn": "8806145045",
            "language_code": "spa",
            "num_pages": 96,
            "ratings_count": 234567,
            "average_rating": 4.23,
            "publication_date": "1924",
            "publisher": "Einaudi",
            "description": "Poesie d'amore appassionate e malinconiche. Amore, passione, tristezza, desiderio"
        },
        
        # Biography/Memoir
        {
            "id": "39",
            "title": "Diario di Anna Frank",
            "authors": ["Anne Frank"],
            "isbn": "0553296981",
            "language_code": "dut",
            "num_pages": 283,
            "ratings_count": 3456789,
            "average_rating": 4.18,
            "publication_date": "1947",
            "publisher": "Einaudi",
            "description": "Testimonianza dell'Olocausto. Storia vera, guerra, speranza, gioventÃ¹"
        },
        
        # Fantasy Modern
        {
            "id": "40",
            "title": "Il Nome del Vento",
            "authors": ["Patrick Rothfuss"],
            "isbn": "0756404746",
            "language_code": "eng",
            "num_pages": 662,
            "ratings_count": 876543,
            "average_rating": 4.55,
            "publication_date": "2007",
            "publisher": "Fanucci",
            "description": "Fantasy epico su un leggendario avventuriero. Magia, musica, mistero, avventura"
        },
        
        # Psychological
        {
            "id": "41",
            "title": "L'Insostenibile Leggerezza dell'Essere",
            "authors": ["Milan Kundera"],
            "isbn": "0061148520",
            "language_code": "cze",
            "num_pages": 314,
            "ratings_count": 345678,
            "average_rating": 3.98,
            "publication_date": "1984",
            "publisher": "Adelphi",
            "description": "Riflessioni filosofiche sull'amore e la vita. Amore, esistenza, scelte, libertÃ "
        },
        
        # Crime/Noir
        {
            "id": "42",
            "title": "Il Corvo",
            "authors": ["Massimo Carlotto"],
            "isbn": "8806210416",
            "language_code": "ita",
            "num_pages": 192,
            "ratings_count": 12345,
            "average_rating": 3.72,
            "publication_date": "2005",
            "publisher": "Einaudi",
            "description": "Noir italiano ambientato a Padova. Crimine, vendetta, noir, indagine"
        },
        
        # Classics
        {
            "id": "43",
            "title": "Delitto e Castigo",
            "authors": ["Fyodor Dostoevsky"],
            "isbn": "0143058142",
            "language_code": "rus",
            "num_pages": 671,
            "ratings_count": 765432,
            "average_rating": 4.22,
            "publication_date": "1866",
            "publisher": "Einaudi",
            "description": "Dramma psicologico su colpa e redenzione. Crimine, morale, coscienza, tragico"
        },
        {
            "id": "44",
            "title": "I Fratelli Karamazov",
            "authors": ["Fyodor Dostoevsky"],
            "isbn": "0374528373",
            "language_code": "rus",
            "num_pages": 796,
            "ratings_count": 456789,
            "average_rating": 4.34,
            "publication_date": "1880",
            "publisher": "Einaudi",
            "description": "Epica familiare su fede e dubbio. Filosofia, famiglia, tragedia, religione"
        },
        
        # Self-help/Motivation
        {
            "id": "45",
            "title": "Le 7 Regole per Avere Successo",
            "authors": ["Stephen Covey"],
            "isbn": "0743269519",
            "language_code": "eng",
            "num_pages": 381,
            "ratings_count": 234567,
            "average_rating": 4.12,
            "publication_date": "1989",
            "publisher": "Franco Angeli",
            "description": "Guida al miglioramento personale e professionale. Crescita, efficacia, abitudini, successo"
        },
    ]
    
    return books


def load_books_from_csv(csv_path: str) -> List[Dict]:
    """Load books from CSV file (Kaggle Books Dataset)"""
    import pandas as pd
    
    try:
        df = pd.read_csv(csv_path)
        books = []
        for _, row in df.iterrows():
            authors = str(row.get('authors', '')).split(',')
            authors = [a.strip() for a in authors if a.strip()]
            
            book = {
                "id": str(row.get('bookID', row.name)),
                "title": str(row.get('title', '')),
                "authors": authors,
                "isbn": str(row.get('isbn', '')) if pd.notna(row.get('isbn')) else None,
                "language_code": str(row.get('language_code', '')) if pd.notna(row.get('language_code')) else None,
                "num_pages": int(row.get('num_pages', 0)) if pd.notna(row.get('num_pages')) else None,
                "ratings_count": int(row.get('ratings_count', 0)) if pd.notna(row.get('ratings_count')) else 0,
                "average_rating": float(row.get('average_rating', 0)) if pd.notna(row.get('average_rating')) else 0.0,
                "publication_date": str(row.get('publication_date', '')) if pd.notna(row.get('publication_date')) else None,
                "publisher": str(row.get('publisher', '')) if pd.notna(row.get('publisher')) else None,
                "description": str(row.get('description', '')) if pd.notna(row.get('description')) else None,
            }
            books.append(book)
        
        return books
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return generate_sample_books()
