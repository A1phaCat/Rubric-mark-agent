---
title: "GreenRoute: An AI Advisor for Lower-Emission Freight Routes"
subtitle: "ELEC5623 Group Business Proposal · Track A — AI Agent Product"
team: "Group 25"
---

| Cover information | |
|---|---|
| Track | A — AI Agent Product |
| Group | 25 |
| Members | Sophie Taylor (530601184), James Liu (530597342), Ahmed Hassan (530605519), Emma Wilson (530592867), Ryan Patel (530608041) |
| Lab tutor and approval | Dr K. Morrison — approved 29 August 2026 |
| Product vision | Help freight companies cut emissions with AI. |

## 1. Executive Summary

Transport is a major source of greenhouse gas emissions. GreenRoute is an AI agent that helps freight companies choose routes with lower emissions. The user enters a delivery job and GreenRoute suggests a greener route and explains why. This helps companies meet sustainability goals and save fuel.

## 2. Background

Freight companies plan many deliveries every day. Climate change is an important issue and companies are under pressure to reduce emissions. AI can help with many problems including logistics.

## 3. Problem Statement

Freight companies do not know which routes have the lowest emissions. GenAI can explain route choices in natural language so that dispatchers understand them.

## 4. Requirements

Users are dispatchers at freight companies.

| ID | Requirement |
|---|---|
| FR1 | User can enter a delivery job |
| FR2 | System suggests routes |
| FR3 | System estimates emissions for each route |
| FR4 | System explains the suggestion |
| FR5 | User can compare routes |
| NFR1 | System should be fast |
| NFR2 | System should be accurate |
| NFR3 | System should be user-friendly |

## 5. Proposed Product

GreenRoute is a web app. The dispatcher enters the origin, destination and vehicle type. The system gets candidate routes from a routing API, estimates the emissions of each route from distance, vehicle type and expected traffic, and then an LLM agent compares the routes and writes a recommendation with an explanation. The agent can also answer follow-up questions such as "what if we leave two hours later?" by calling the routing tool again.

## 6. Methodology

We will use Python, a routing API such as OpenRouteService, and an LLM API. Emissions will be estimated with a simple formula based on fuel consumption per kilometre for each vehicle type. We will use an agile approach.

## 7. Business Analysis

GreenRoute saves fuel and reduces emissions, which is good for companies and the environment. Companies could pay a monthly subscription.

## 8. Evaluation

We will test GreenRoute on some example delivery jobs and check that the recommendations make sense. We will also ask some people to try it.

## 9. Risks

The emissions estimates may not be accurate. The routing API may have limits.

## 10. Plan

| Weeks | Work |
|---|---|
| 5–8 | Build the system |
| 9–11 | Test and improve |
| 12–13 | Final report and presentation |

## 11. References

International Energy Agency. (2023). *Tracking clean energy progress 2023*. IEA.

OpenRouteService. https://openrouteservice.org
