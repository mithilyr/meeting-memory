---
title: Meeting Memory
emoji: 🗂️
colorFrom: yellow
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: Ask 138 meetings questions; every answer quotes its source.
---

# Meeting Memory (hosted demo)

Ask questions of 138 recorded meetings (AMI Meeting Corpus), browse each project's timeline of
decisions, and read the brief a team gets before its next meeting. Every quote in an answer is checked
word for word against the transcript before it is shown.

This copy is read-only: it can't take new meetings, and each visitor can ask 20 questions an hour so the
free model quota lasts. If the daily model quota is spent, the page says so and still shows the matching
transcript passages word for word.

Code, write-up and run instructions: https://github.com/mithilyr/meeting-memory

Data: AMI Meeting Corpus, University of Edinburgh and partners, CC BY 4.0. Transcripts are reformatted, not edited.
