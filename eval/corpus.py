"""Benchmark corpus: AI-styled originals and faithful hand revisions (thermal science).

Every faithful revision must pass compare() with zero errors — that is the
false-positive test. Errors are then injected into the faithful revisions.
Replace or extend with paragraphs from your own papers (see README).
"""

PAIRS = [
    ("p01-chf-mass-flux",
     r"In recent years, the critical heat flux (CHF) of flow boiling in microchannels has attracted increasing attention \cite{kandlikar2002,qu2003}. Our experiments clearly show that the CHF increased from 410 kW/m2 to 585 kW/m2 when the mass flux was raised from 200 kg/(m2·s) to 400 kg/(m2·s), under the investigated conditions. These findings suggest that higher mass flux may delay dryout.",
     r"The critical heat flux (CHF) of flow boiling in microchannels has been studied extensively \cite{kandlikar2002,qu2003}. Under the investigated conditions, the CHF increased from 410 kW/m2 to 585 kW/m2 as the mass flux was raised from 200 kg/(m2·s) to 400 kg/(m2·s). These findings suggest that a higher mass flux may delay dryout."),

    ("p02-md-waiting-time",
     r"Molecular dynamics (MD) simulations were performed for argon confined between copper walls separated by 20 nm \cite{yamamoto2014}. The results demonstrate that nucleation occurred within approximately 0.6 ns on the hydrophilic wall ($\theta = 35^\circ$), whereas no bubble formed on the hydrophobic wall within 2 ns. This indicates that the waiting time is less than 1 ns for strongly wetting surfaces in the present simulations.",
     r"Molecular dynamics (MD) simulations were performed for argon confined between copper walls separated by 20 nm \cite{yamamoto2014}. On the hydrophilic wall ($\theta = 35^\circ$), nucleation occurred within approximately 0.6 ns, whereas no bubble formed on the hydrophobic wall within 2 ns. In the present simulations, the waiting time on strongly wetting surfaces is therefore less than 1 ns."),

    ("p03-htc-nanostructure",
     r"It is worth noting that the nanostructured surface significantly enhanced the heat transfer coefficient (HTC) by 38\% at a wall superheat of 12 K compared with the plain surface \cite{chen2009}. This remarkable improvement can be attributed to the increased nucleation site density, which was approximately 2.5 times higher than that of the plain surface.",
     r"At a wall superheat of 12 K, the nanostructured surface increased the heat transfer coefficient (HTC) by 38\% relative to the plain surface \cite{chen2009}. This improvement can be attributed to the higher nucleation site density, approximately 2.5 times that of the plain surface."),

    ("p04-pressure-drop",
     r"The two-phase pressure drop in the microchannel increased dramatically with heat flux, rising from 8.2 kPa to 15.6 kPa as the heat flux increased from 50 kW/m2 to 150 kW/m2. These results prove that flow instabilities become dominant at heat fluxes above 120 kW/m2 in this study.",
     r"As the heat flux increased from 50 kW/m2 to 150 kW/m2, the two-phase pressure drop in the microchannel rose from 8.2 kPa to 15.6 kPa. These results show that flow instabilities become dominant at heat fluxes above 120 kW/m2 in this study."),

    ("p05-contact-angle-onb",
     r"Interestingly, the contact angle decreased from 92° to 18° after plasma treatment, which may explain the lower wall superheat at the onset of nucleate boiling (ONB) observed in Fig.~\ref{fig:onb}. However, ONB was delayed by about 3 K on the aged samples, suggesting that the coating could degrade within 30 days.",
     r"After plasma treatment, the contact angle decreased from 92° to 18°, which may explain the lower wall superheat at the onset of nucleate boiling (ONB) in Fig.~\ref{fig:onb}. On the aged samples, however, ONB was delayed by about 3 K, suggesting that the coating could degrade within 30 days."),

    ("p06-itr",
     r"The interfacial thermal resistance (ITR) between water and the gold substrate was $2.1 \times 10^{-8}$~m$^2$K/W for the hydrophilic case \cite{ge2006}. Our results confirm that the ITR is reduced by 45\% when the solid--liquid interaction strength is doubled, which might be related to the denser adsorption layer.",
     r"For the hydrophilic case, the interfacial thermal resistance (ITR) between water and the gold substrate was $2.1 \times 10^{-8}$~m$^2$K/W \cite{ge2006}. Doubling the solid--liquid interaction strength reduced the ITR by 45\%, which might be related to the denser adsorption layer."),

    ("p07-friction-factor",
     r"For Reynolds numbers between 300 and 2000, the friction factor of the microchannel agreed with the conventional correlation within 10\%, indicating that conventional theory remains applicable in the range studied. It should be noted that the deviation exceeded 25\% for the smallest hydraulic diameter of 50 μm.",
     r"For Reynolds numbers between 300 and 2000, the friction factor of the microchannel agreed with the conventional correlation within 10\%, indicating that conventional theory remains applicable in the range studied. For the smallest hydraulic diameter of 50 μm, however, the deviation exceeded 25\%."),

    ("p08-departure",
     r"When the inlet subcooling was reduced from 20 K to 5 K, the bubble departure diameter grew from 0.42 mm to 0.71 mm, and the departure frequency fell below 40 Hz. This trend is consistent with previous visualizations \cite{situ2005,thorncroft1998}.",
     r"Reducing the inlet subcooling from 20 K to 5 K increased the bubble departure diameter from 0.42 mm to 0.71 mm and lowered the departure frequency to below 40 Hz, consistent with previous visualizations \cite{situ2005,thorncroft1998}."),

    ("p09-biphilic",
     r"A novel hybrid wettability surface was fabricated and tested in pool boiling of water at atmospheric pressure \cite{betz2013}. The CHF reached 182 W/cm2, approximately 1.6 times that of the bare copper surface, while the heat transfer coefficient increased by 74\%. These results demonstrate the potential of biphilic designs for electronics cooling.",
     r"A hybrid wettability surface was fabricated and tested in pool boiling of water at atmospheric pressure \cite{betz2013}. The CHF reached 182 W/cm2, approximately 1.6 times that of the bare copper surface, and the heat transfer coefficient increased by 74\%. These results indicate the potential of biphilic designs for electronics cooling."),

    ("p10-model-validation",
     r"At low heat fluxes, the predicted wall temperature deviated from the measurements by less than 1.5 K, which suggests that the model captures the single-phase region well. At higher heat fluxes, the deviation might be attributed to the neglected axial conduction in the 0.5 mm thick wall.",
     r"At low heat fluxes, the predicted wall temperature deviated from the measurements by less than 1.5 K, suggesting that the model captures the single-phase region well. At higher heat fluxes, the larger deviation might be attributed to the neglected axial conduction in the 0.5 mm thick wall."),
]
