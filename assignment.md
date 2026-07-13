# Assignment: Email Ingestion and Deduplication

## Overview

The goal of this assignment is to create a prototype system that ingests raw email threads at scale and deduplicates them into canonical threads. This assignment reflects challenges encountered in real-world email ingestion but is simplified for prototyping purposes.

## Problem Description

When ingesting emails from multiple sources within an organization, several challenges arise:

- **Duplicates:** Multiple copies of the same email may exist.
- **Near-Duplicates:** Variations in formatting, whitespace, encoding, or parsing differences due to differences between email servers.
- **Threading Complexity:** Emails form threads through replies and forwarded messages.

Your task is to ingest emails and construct a structured repository that eliminates redundant emails while preserving thread relationships.

## Example Email Threads

Raw email threads (`doc1`, `doc2`, etc) can be modeled as follows:

```
doc1: 0
doc2: 0-1
doc3: 0-1m
doc4: 0-1-2
doc5: 0-1-2m
```

Each document represents an internal sequence of emails in a thread. A suffix of `"m"` indicates a slightly modified version of an email (e.g., a near-duplicate due to minor formatting changes).

### Example Breakdown

- **doc1:** Contains a single email (`0`)
- **doc2:** Extends doc1 with a reply (`0-1`)
- **doc3:** A slightly modified version of doc2 (`0-1m`)
- **doc4:** Extends doc2 with another reply (`0-1-2`)
- **doc5:** A slightly modified version of doc4 (`0-1-2m`)

For simplicity purposes, we will not distinguish between the type of thread relationship (e.g., reply or forward).

## Expected Output

The system should generate canonical threads that group identical or near-identical email sequences together while preserving the hierarchy of replies. The near-deduplicated data structure should preserve the following relationships between canonical threads and original raw documents:

### Canonical Threads

**Canon0:**
- doc1: `0`

**Canon1:**
- doc2: `0-1`
- doc3: `0-1m`

**Canon2:**
- doc4: `0-1-2`
- doc5: `0-1-2m`

### Hierarchical Structure

Finally, the canonical chains must be linked together according to the chain hierarchy. In the example above, Canon2 is a child of Canon1, which is a child of Canon0, i.e.:

```
Canon0 → Canon1 → Canon2
```

## Implementation Requirements

### 1. Data Ingestion

- Develop an ingestion pipeline that processes raw email threads as they are retrieved.
- Use multiple workers for parallel processing, using a Kubernetes deployment.

### 2. Canonical Thread Construction

- Identify and group near-duplicate email threads together into canonical threads.
- Maintain a mapping of raw documents to their respective canonical thread.
- Maintain hierarchy (parent/child) links between canonical threads.
- Construct these threads in real time as documents are ingested.

### 3. Data Storage/Queries

Store the resulting canonical thread structure in a database of your choice, using a representation of your choice.

Ensure that queries can efficiently retrieve:

- A canonical thread id given any raw document id (document id is the filename).
- A set of raw document ids, given a canonical thread id.
- The parents/children canonical thread ids of a given canonical thread.

## Data and Evaluation

You are provided two directories:

- `test`
- `eval`

The `test` directory contains raw files named `docXXXX.txt`, similar to the examples above, but without any ground truth, i.e., its thread structure is unknown.

The `eval` directory provides a sample of threads that contain ground truth, which can be useful for testing and evaluation. Filenames in the `eval` directory mimic the structure of the examples above, e.g.:

```
5.txt
5_1m.txt
5_1.txt
5_1_2.txt
5_1_2m.txt
```

The filenames show the decomposed structure of the thread. For example, you can infer that `5_1m` and `5_1` belong to the same canonical thread since they contain the same emails (except for small variations between `1` and `1m`).

Evaluate the performance of your near deduplication using the gold standard in the `eval` directory. Note — it doesn't have to be 100%.

## Evaluation Criteria

Your submission will be evaluated based on:

- **Correctness:** Does it correctly (even if not 100%) identify duplicate and near-duplicate threads?
- **Efficiency:** Can it handle multiple email threads in real-time ingestion?
- **Scalability:** Is the approach extensible to larger datasets?

Note — the implementation should only reflect certain design choices, but it is expected to be a quick and dirty prototype, so shortcuts to make it easy to implement are expected. It does not actually have to be able to scale to very large collections.

## Notes

- You are free to use any programming language and database.
- The focus is on a quick and dirty prototype rather than a production-grade system.
- Feel free to make reasonable assumptions.
- Feel free to reach out with any questions.
