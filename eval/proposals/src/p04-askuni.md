---
title: "AskUni: An AI Chatbot for Student Questions"
subtitle: "ELEC5623 Group Business Proposal · Track A — AI Agent Product"
team: "Group 19"
---

| Cover information | |
|---|---|
| Track | A — AI Agent Product |
| Group | 19 |
| Members | Lucas Pereira (530402215), Yuki Sato (530398774), Ben Clarke (530410036), Amelia Scott (530395581), Ravi Kumar (530407713) |
| Lab tutor and approval | Dr K. Morrison — approved 28 August 2026 |
| Product vision | Students can ask any question about university life and get an answer straight away. |

## 1. Executive Summary

University students have lots of questions about enrolment, timetables, assessments, special consideration, IT services and campus facilities. Finding answers on university websites can be frustrating. AskUni is an AI chatbot that answers student questions instantly using a large language model. Students type a question into a chat window and AskUni replies in a friendly way. This will save students time and reduce the number of emails sent to student services.

## 2. Introduction and Background

Universities have large websites with many pages and it is not always easy to find information. Students often ask friends or post on social media instead. AI chatbots like ChatGPT have become very popular and are good at answering questions in natural language, so it makes sense to use one for student questions. Many companies now use chatbots for customer service.

### 2.1 The Rise of Chatbots

Chatbots have existed for decades, from early rule-based programs to the voice assistants on today's phones. The release of ChatGPT in late 2022 changed public expectations: people now expect to be able to ask a question in their own words and receive a complete, conversational answer. Many organisations including banks, airlines, telecommunications companies and online retailers now offer chat assistants on their websites, and students use AI chat tools daily for study and everyday tasks. It is natural that students would also expect this kind of experience from their university.

### 2.2 Student Experience

Starting university involves learning a large number of new systems and rules. Students need to understand enrolment, units of study, timetables, assessment submission, special consideration, academic integrity, library services, IT accounts, printing, campus maps, clubs and societies, and support services. Information about these topics is spread across many web pages, and the language used on official pages can be formal. International students may also be adjusting to a new country and education system at the same time. A friendly assistant that can answer questions in plain language would make the transition easier.

## 3. Problem Statement and Motivation

### 3.1 Problem

Students find it hard to get answers to their questions quickly.

### 3.2 Who Is Affected

All students, especially new and international students, and student services staff who answer the same questions repeatedly.

### 3.3 Why GenAI

Large language models can understand questions written in everyday language and give fluent answers, which is better than a search box. They are available all the time.

## 4. Stakeholders and Requirements

### 4.1 Stakeholders

| Stakeholder | Type | Need |
|---|---|---|
| Undergraduate students | Primary | Quick answers to administrative questions |
| International students | Primary | Answers in plain English, available outside business hours |
| Student services staff | Secondary | Fewer repetitive enquiries |
| IT services | Secondary | A tool that is secure and easy to maintain |

### 4.2 Use Cases

- UC1: A student asks when the census date is.
- UC2: A student asks how to apply for special consideration.
- UC3: A student asks where to print on campus.
- UC4: A student asks a follow-up question in the same conversation.
- UC5: A student rates an answer.

### 4.2a Personas

**Mei, first-year international student.** Mei arrived in Sydney two weeks before semester. She is unsure how to change a tutorial time and does not know which office handles it. She prefers to ask questions in writing rather than on the phone.

**Josh, second-year domestic student.** Josh works part-time and studies in the evenings. He needs answers outside business hours, for example about the deadline for special consideration when he becomes ill the night before an exam.

**Priya, student services officer.** Priya answers enquiries by email and at the front desk. Many questions are the same each week, especially at the start of semester.

### 4.3 Scope

In scope: a web chat for current students covering administrative and campus questions. Out of scope: questions about individual student records (results, fees owing), course content questions, and integration with the student system.

### 4.4 Functional Requirements

| ID | Requirement | Priority | Owner | Acceptance criterion |
|---|---|---|---|---|
| FR1 | Provide a chat window on a web page | Must | A1 | Page loads and accepts text input |
| FR2 | Send the question to the language model | Must | A1 | Reply returned for 100% of test questions |
| FR3 | Display the answer in the chat | Must | A1 | Answer shown under the question |
| FR4 | Keep conversation history in a session | Must | A2 | Follow-up questions use previous turns |
| FR5 | Let the user clear the conversation | Should | A2 | History cleared on request |
| FR6 | Store conversations for analysis | Should | A2 | Conversations saved with timestamps |
| FR7 | Let the user rate an answer | Should | A3 | Rating saved |
| FR8 | Show a disclaimer that answers may be wrong | Must | A3 | Disclaimer visible on every page |
| FR9 | Provide a link to contact student services | Must | A3 | Link visible in the chat |
| FR10 | Support mobile browsers | Should | A4 | Usable at 375 px width |
| FR11 | Show suggested starter questions | Could | A4 | Five starter questions shown |
| FR12 | Show typing indicator while waiting | Could | A4 | |
| FR13 | Provide an admin page showing usage statistics | Should | A5 | Daily question counts displayed |
| FR14 | Let admins see low-rated answers | Should | A5 | Answers rated 1–2 listed |
| FR15 | Let admins change the system prompt | Could | A5 | |

### 4.5 Non-Functional Requirements

| ID | Requirement | Target |
|---|---|---|
| NFR1 | Response time | Answer within 5 seconds for 90% of questions |
| NFR2 | Availability | Available 24/7 during the demonstration period |
| NFR3 | Usability | Students can ask a question without instructions |
| NFR4 | Privacy | No student ID or name requested |
| NFR5 | Cost | Under $50 of API usage for the semester |

### 4.6 Constraints

1. Must use a hosted LLM API because the team has no GPU.
2. Must be completed within the semester.
3. No access to university student systems.

## 5. Proposed Product and Innovation

AskUni is a chat website. The student types a question and the system sends it to a large language model with a system prompt telling the model to act as a helpful university assistant. The model's answer is shown in the chat. Conversation history is sent with each new question so that follow-up questions work.

What makes AskUni different from using ChatGPT directly is that it is focused on university questions through its system prompt, it has a friendly interface designed for students, and it includes an admin page.

### 5.1 Interface Design

The chat page has a header with the AskUni name and logo, a message area, a text box with a send button and a row of starter questions. Answers appear in speech bubbles with a small thumbs-up/thumbs-down rating under each one. A banner at the bottom reminds students that answers may not always be correct and gives the student services contact link. On mobile phones the starter questions collapse into a horizontal scroll.

### 5.2 System Prompt

The system prompt is: "You are AskUni, a friendly and helpful assistant for university students. Answer questions about university life clearly and concisely. If you are not sure, suggest the student contacts student services." The prompt can be changed by admins (FR15).

## 6. Methodology and System Design

We will use a React front end and a Node.js back end. The back end receives the question, adds the system prompt and history, calls the OpenAI API and returns the answer. Conversations are stored in a database. We will develop iteratively and test as we go.

## 7. Business and Product Analysis

### 7.1 Value Proposition

Instant answers for students at any time, and fewer repetitive enquiries for staff.

### 7.2 Alternatives

Students can already use the university website search, the FAQ pages and the student services phone line. These are slower than a chatbot or only available in business hours. Students can also use ChatGPT directly, but it does not focus on university questions.

### 7.3 Benefits and Costs

Benefits are time saved for students and staff. Costs are API fees, which are low, and hosting.

## 8. Evaluation Plan

We will test AskUni with 30 typical student questions written by the team and check whether answers are correct and helpful. We will measure average response time and ask 10 students to try the chatbot and give a rating out of 5. Success means answers are mostly correct, average rating is at least 4, and response time meets NFR1.

## 9. Risks, Ethics and Responsible AI

| Risk | Mitigation |
|---|---|
| The model gives wrong information | Disclaimer and link to student services |
| Students enter personal information | Privacy notice; no storage of identifiers |
| API costs are higher than expected | Monitor usage; set a spending limit |
| Inappropriate use of the chatbot | Moderation through the API's content filter |

## 10. Semester Plan and Team Responsibilities

| Week | Task |
|---|---|
| 5–6 | Set up front end and back end |
| 7–8 | Chat and history working |
| 9–10 | Ratings, admin page, mobile layout |
| 11 | Testing with students |
| 12 | Fixes and report |
| 13 | Presentation |

| Area | Member | Responsibility |
|---|---|---|
| A1 | Lucas Pereira | Chat interface and API connection |
| A2 | Yuki Sato | Conversation history and storage |
| A3 | Ben Clarke | Ratings, disclaimer and contact link |
| A4 | Amelia Scott | Mobile layout and starter questions |
| A5 | Ravi Kumar | Admin page |

## 11. References

OpenAI (2023). GPT-4 Technical Report. arXiv:2303.08774.

Kasneci et al., ChatGPT for good? On opportunities and challenges of large language models for education, Learning and Individual Differences 2023.

## Appendix A — Example Conversations

**Student:** When is the census date this semester?
**AskUni:** The census date is usually around the end of the fourth week of semester. After the census date you will be charged for units you are enrolled in. Please check the university's key dates page to confirm the exact date.

**Student:** How do I apply for special consideration?
**AskUni:** You can usually apply for special consideration online through the student portal. You will need supporting documentation such as a medical certificate, and applications generally need to be submitted within a few days of the affected assessment.

**Student:** Where can I print on campus?
**AskUni:** Most universities have printers in the library and computer labs. You can usually print using your student card after adding credit to your printing account.

## Appendix B — Admin Page

The admin page shows the number of questions asked each day, the average rating, a list of the lowest-rated answers with the question that produced them, and a text box to edit the system prompt. It is protected by a simple password for the demonstration.

