# TODO

## Updates
- [ ] Make sure `data/entries/{topics}.txt` updates only when there are significant changes *(Definition of "significant" needed)*.
- [ ] Make sure all Python scripts add to existing files instead of overwriting them, and if possible, make changes only when there are significant changes *(Again, definition of "significant" needed)*.

## Format
- [ ] Have `synthesizeData.py` make the synthesized data look like a Wikipedia article.
    - [ ] Sample structure for historical figures:
        - Infobox
        - Lead section
        - Early life and education
        - Career
        - Personal life
        - Legacy
        - See also
        - References
    - [ ] Sample structure for landmarks:
        - Infobox
        - Lead section
        - History
        - Architecture
        - Cultural significance
        - See also
        - References
    - [ ] Sample structure for events:
        - Infobox
        - Lead section
        - Background
        - Course of events
        - Aftermath
        - See also
        - References
    - [ ] Sample structure for cultural narratives:
        - Infobox
        - Lead section
        - Origins
        - Development
        - Impact
        - See also
        - References

## Sources
- [ ] Add a list of credible sources to find (e.g. Brittanica, etc.).
- [ ] Make sure `synthesizeData.py` uses these sources.

## Content
- [ ] Make sure synthesized data has basic information in the infobox (name, date, location, etc.)