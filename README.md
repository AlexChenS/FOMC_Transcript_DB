# FOMC Meeting Transcript DB

A MongoDB-backed pipeline that scrapes, stores, and analyzes Federal Open Market
Committee (FOMC) meeting minutes from 1993 to the present, using NLP topic
modeling to trace how the Fed's policy focus has shifted over time.

## Overview

The project builds a document store of FOMC transcripts and layers a text-mining
pipeline on top of it:

1. **Scrape** meeting dates and minutes from federalreserve.gov, handling three
   different site layouts across the historical, transitional, and modern eras
   (1993–1995, 1995–2007, 2008–present).
2. **Store** raw metadata and transcript text in MongoDB, with a unique index on
   meeting date and a full-text index over the raw transcript for keyword search.
3. **Clean & tokenize** each transcript with spaCy (lemmatization, POS filtering,
   custom FOMC-specific stopwords) to produce a clean token collection.
4. **Model** topics across the corpus with gensim: bigram phrase detection, then
   LDA topic modeling with coherence-based tuning to choose the number of topics.
5. **Analyze & visualize** the dominant topic per document and per year, and
   render an interactive pyLDAvis visualization of the topic space.

## Data model (MongoDB, `fomc` database)

- `fomc_metadata` — meeting date, year, source URL, scrape status
- `fomc_minutes_raw` — raw scraped transcript text, chair, scrape timestamp
- `fomc_minutes_clean` — lemmatized tokens, token count, topic distribution,
  dominant topic per document
- `fomc_lda_metadata` — trained model parameters, topic-word distributions,
  coherence score

## Findings

Topic modeling (4 topics, coherence ≈ 0.53) recovers an interpretable
progression in FOMC discourse: early minutes cluster around economic
growth/productivity, the 2001–2002 minutes shift toward economic downturn
language, and minutes from 2004 onward are dominated by quantitative
easing/asset-purchase topics.

## Tech stack

Python, MongoDB (`pymongo`), `requests`/`BeautifulSoup` (scraping), `spaCy` and
`nltk` (text cleaning), `gensim` (bigram phrases, LDA, coherence), `pyLDAvis`
(visualization).

## Files

- [db_setup.py](db_setup.py) — MongoDB connection and collection setup
- [db_manager.py](db_manager.py) — scraping, cleaning, tokenization, and LDA pipeline (`DB_Manager` class)
- `*_by_year.txt`, `LDA_topics.txt`, `LDA_tuning.txt`, `bigrams.txt`, `topic_distribution.txt` — pipeline output logs
- [lda_visualization.html](lda_visualization.html) — interactive pyLDAvis topic visualization
