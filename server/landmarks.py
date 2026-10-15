"""Short editorial summaries of well-known Supreme Court judgments, and reading notes for a few dense sections.

These are written by the LexBharat team, NOT taken from the judgment text. They state only the widely reported core holding.
They are shown on the case page (labelled) and given to KanoonBuddy so it does not have to infer a landmark's holding from raw passages.
A lawyer should check them against the judgment before they are relied on in court.
"""

EDITORIAL_NOTE = ("Editor's summary, written by LexBharat. It is not part of the judgment. Read the judgment below and check "
                  "this summary against it before you rely on it.")

LANDMARKS = {
    "1973_INSC_91": ("Kesavananda Bharati v. State of Kerala (1973), 13-judge bench, decided 7-6",
                     "Parliament's power to amend the Constitution under Article 368 is wide and reaches the Fundamental Rights, but it cannot be used "
                     "to destroy or alter the 'basic structure' (basic features) of the Constitution. The Court overruled the view in Golak Nath (1967) "
                     "that Fundamental Rights could not be amended. Which features form the basic structure was left to be decided case by case."),
    "1967_INSC_45": ("I.C. Golak Nath v. State of Punjab (1967), decided 6-5",
                     "The Court held that Parliament could not amend the Fundamental Rights, treating a constitutional amendment as 'law' under Article 13. "
                     "This view was overruled in Kesavananda Bharati (1973)."),
    "1978_INSC_16": ("Maneka Gandhi v. Union of India (1978)",
                     "The 'procedure established by law' in Article 21 must be fair, just and reasonable, not arbitrary or oppressive. Articles 14, 19 and 21 "
                     "are not separate compartments: a law that affects personal liberty must satisfy all of them. The power to impound a passport must be "
                     "exercised fairly and subject to natural justice, including a hearing."),
    "1975_INSC_272": ("Indira Nehru Gandhi v. Raj Narain (1975)",
                      "The Court struck down clause (4) of Article 329A, inserted by the 39th Amendment to put the Prime Minister's election beyond judicial "
                      "review, because it violated the basic structure (free and fair elections, the rule of law and judicial review). Mrs Gandhi's election "
                      "was upheld on the basis of the amended election law, not on that clause."),
    "1980_INSC_142": ("Minerva Mills Ltd. v. Union of India (1980)",
                      "The Court struck down section 55 of the 42nd Amendment (clauses 4 and 5 added to Article 368), holding that Parliament's amending power "
                      "is limited and that this limit is itself part of the basic structure. It also struck down section 4 of that Amendment and held that "
                      "the balance between Fundamental Rights and the Directive Principles is part of the basic structure."),
    "2017_INSC_801": ("Justice K.S. Puttaswamy (Retd.) v. Union of India (2017), nine-judge bench",
                      "The Court unanimously held that the right to privacy is a fundamental right, protected under Article 21 as part of the right to life "
                      "and personal liberty, and by the freedoms in Part III of the Constitution. It overruled M.P. Sharma and Kharak Singh to the extent "
                      "they held otherwise."),
    "2018_INSC_790": ("Navtej Singh Johar v. Union of India (2018)",
                      "A Constitution Bench read down Section 377 of the IPC and held it unconstitutional insofar as it criminalised consensual sexual "
                      "conduct between adults of the same sex."),
    "1980_INSC_68": ("Gurbaksh Singh Sibbia v. State of Punjab (1980), Constitution Bench",
                     "The power to grant anticipatory bail under Section 438 of the CrPC (now Section 482 of the BNSS) is wide. It should not be hemmed in by "
                     "rigid conditions or a fixed time limit; each case is decided on its own facts and the court's discretion."),
    "2014_INSC_463": ("Arnesh Kumar v. State of Bihar (2014)",
                      "In offences punishable with imprisonment of up to seven years (such as Section 498A of the IPC), the police should not arrest "
                      "automatically. They must be satisfied that arrest is necessary under Section 41 of the CrPC (now Section 35 of the BNSS) and record "
                      "their reasons, and Magistrates must check that this was done before authorising detention."),
    "2022_INSC_690": ("Satender Kumar Antil v. CBI (2022)",
                      "The Court issued guidelines on bail, grouping offences by seriousness, directed courts to avoid unnecessary arrests and stressed that "
                      "bail, not jail, is the rule. It suggested that the Government consider a separate law on bail."),
    "1997_INSC_604": ("Vishaka v. State of Rajasthan (1997)",
                      "In the absence of a law, the Court laid down binding guidelines to prevent sexual harassment of women at the workplace, relying on "
                      "Articles 14, 15, 19(1)(g) and 21 and the CEDAW convention. They applied until Parliament passed the Sexual Harassment of Women at "
                      "Workplace Act, 2013."),
    "1992_INSC_357": ("State of Haryana v. Bhajan Lal (1992)",
                      "The Court listed categories of cases in which an FIR or complaint may be quashed under Section 482 of the CrPC (now Section 528 of "
                      "the BNSS) or Article 226, for example where the allegations, even if taken as true, disclose no offence, or where the proceeding is "
                      "clearly malicious. It stressed that the power is to be used sparingly."),
}

# Dense sections that language models often misread. Each note was checked against the section text.
SECTION_NOTES = {
    ("BNSS", "187"): ("Reading guide: police custody can be authorised for 15 days in total, in whole or in parts, within the first 40 days (of a 60-day "
                      "period) or the first 60 days (of a 90-day period), under sub-section (2). The 90 and 60 days in sub-section (3) are the maximum TOTAL "
                      "detention (police and judicial custody together), after which the accused must be released on bail if willing to furnish it."),
}


def summary_for(case_id: str):
    """(heading, text) for a landmark case, else None."""
    return LANDMARKS.get(case_id)


def note_for(act: str, number: str):
    return SECTION_NOTES.get((act, number))
