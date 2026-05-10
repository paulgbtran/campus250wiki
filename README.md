# campus250wiki

## Project overview
An agentic AI system that gathers, learns, and present Philadelphia's 250 years of history interactively. The process of gathering, learning, presenting, and documenting Philadelphia will be fully automated in predefined intervals.

## Requirements
- Start with a query asking to list all historical figures, landmarks, events, and cultural narratives/shifts related to Philadelphia in a text file, one line for each entry.
- A searching agent used to search for legitimate sources about Philadelphia's history. This will be used for the works cited section at the end of the page.
- A summarizing agent used to summarize the content from the sources. The summary itself will be placed in the body of the web template.
- A few agents to verify and fact check the summarized content against (1) the sources listed in the works cited, and (2) other locations to ensure the information summarized is not biased.
- Another searching agent, this time searching for images, videos, and 3D models (make sure it's CC/public domain) for the interactive boxes/cards.
- Google Street View for locations/landmarks.

## Who's working?
- Dr. Yang Wang (**faculty advisor**)
- Paul Gia-Bảo Trần (**student leader**, in charge of creating the searching agent, works cited agent, and summarizing agent)
- Tentative assignments, meeting required:
    - Victory Kelechi-Nwaogu (fact-checking agent)
    - MyrrhJessica Okwara (web template agent, interactive element design)

## [Some additional tasks to consider doing](TODO.md)

## Notes
- I have gitignored folders created on execution of the scripts, just so the repo doesn't look too messy. For a list of what's ignored, see [.gitignore](.gitignore).
- For the time being, the scripts rely on having a Gemini API key set as a local variable in my machine. For instructions on how to set it up, see [this documentation](https://ai.google.dev/gemini-api/docs/api-key#set-api-env-var).

## Disclaimer
I'm lazy, so...
1. I'm relying on AI to do most of the work (shoutout to [Google Antigravity](https://antigravity.google/)! :D)
2. I'm not expecting something too flashy out of this, and 
3. Even though this is said to be for the 250th anniversary, I'm only aiming for La Salle's open day or something in October, so no worries if we miss the July mark.