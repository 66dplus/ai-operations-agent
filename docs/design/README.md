# Paper design reference

Source: [AI Operations Agent — Product UI](https://app.paper.design/file/01M4BRC73PZXQQDYV1H04MZTAT), page 1, screens 01–06. Created separately for this project on 2026-10-07. The approved owner brief is a white, dark-text, blue-accent Inter interface with a single research entry point.

The six JSON files preserve exact Paper inline JSX exports. `computed-styles.json` preserves the core frame/title/composer/table/panel values. `frontend/app/globals.css` translates these values into responsive CSS. The browser implements semantic forms, table, dialog, live progress and native controls; the mockups use static placeholder company content.

Desktop uses a 1440px canvas, 80px horizontal outer spacing, 820px composer and 720px review panel. Mobile uses a 390px reference, 24px spacing and stacked company results/actions. Browser screenshots in `../verification/` verify the implementation at both sizes. The mockup status bar belongs to the device reference and is not duplicated in the web app.
