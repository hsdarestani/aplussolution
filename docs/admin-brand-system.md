# A+ Solution browser administration

Concept: Personal. Planung. Präzision. The interface combines the precision of staffing operations with a calm, human tone. The existing company logo remains the identity anchor.

## Visual vocabulary

| Role | Value | Use |
| --- | --- | --- |
| Ink | #102e40 | Navigation, primary actions, headings |
| Paper | #f5f4f0 | Workspace background |
| White | #ffffff | Forms, tables, content surfaces |
| Gold | #bc9549 | Focus indicators, selected navigation detail |
| Muted | #677a84 | Supporting text |
| Border | #dfe5e5 | Quiet separation |

Typography uses the system Aptos / Inter / Segoe UI stack without a remote font dependency. Numeric metrics use tabular figures. Containers use 12 to 20 pixel radii; inputs and buttons use 9 to 10 pixels. Shadows are deliberately restrained.

## Application

`data-admin-web` is set only for admin and manager sessions in a browser. Employee, customer and native app sessions do not receive the new UI layer. Shared Ionic inputs, textareas, selects, searches, buttons, modal toolbars, tables and operational surfaces inherit the system. Schedule service and customer colors retain their operational meaning.

The workspace header exposes the current section, Berlin date and profile access. Sidebar navigation keeps existing routes and adds a brand signature. Dashboard hierarchy puts the brand introduction, actual exception counts and daily shortcuts before exception details. No fake activity or invented performance metrics are introduced.

Responsive layouts cover desktop, smaller laptops and mobile browsers. Focus is visible, reduced motion is honored, and destructive actions remain visually distinct.

## Validation

Production TypeScript/Vite build and the existing Vitest suite. Browser regression spec covers 1440, 1024 and 390 pixel widths, overflow, dashboard shortcuts and navigation.
