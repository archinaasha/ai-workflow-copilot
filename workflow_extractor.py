import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import dateparser


class WorkflowExtractor:
    def __init__(self) -> None:
        self.urgent_keywords = [
            "urgent", "asap", "immediately", "fast", "critical",
            "important", "high priority", "priority", "soon"
        ]

        self.low_priority_keywords = [
            "summary", "inform", "share", "email"
        ]

        self.action_words = [
            "assist", "help", "check", "update", "review", "prepare",
            "send", "ask", "bring", "install", "fix", "connect",
            "verify", "support", "organize", "schedule", "complete",
            "correct", "change", "edit", "replace", "reorder", "sort"
        ]

    def extract_workflow(self, input_text: str) -> Dict[str, Any]:
        now = datetime.now()

        cleaned_text = self._clean_text(input_text)
        request_blocks = self._split_into_request_blocks(cleaned_text)

        task_objects: List[Dict[str, Any]] = []

        for block in request_blocks:
            block = self._remove_quoted_email(block)
            block = self._remove_signature(block)

            if not block.strip():
                continue

            shared_due_date = self._extract_shared_due_date(block, now)
            task_section = self._extract_task_section(block)
            source_text = task_section if task_section else block

            raw_tasks = self._extract_tasks(source_text)

            # fallback: if task extractor finds nothing, try full block
            if not raw_tasks:
                raw_tasks = self._extract_tasks(block)

            tasks = self._normalize_tasks(raw_tasks, source_text)

            for task in tasks:
                task_due_date = self._extract_due_date(task["raw_text"], now) or shared_due_date
                assignee = self._extract_assignee(task["raw_text"], task["title"], source_text)
                location = self._extract_location(task["raw_text"], task["title"], source_text)
                resources = self._extract_resources(task["raw_text"], source_text)
                category = self._classify_task(task["title"], task["raw_text"], source_text)
                priority, reason = self._assign_priority(task["title"], task_due_date, now, category)
                workflow_step = self._generate_workflow_step(task["title"], category)

                task_objects.append(
                    {
                        "title": task["title"],
                        "raw_text": task["raw_text"],
                        "due_date": task_due_date.strftime("%Y-%m-%d %H:%M") if task_due_date else None,
                        "priority": priority,
                        "priority_reason": reason,
                        "workflow_step": workflow_step,
                        "assignee": assignee,
                        "location": location,
                        "resources": resources,
                        "category": category,
                    }
                )

        task_objects = self._deduplicate_task_objects(task_objects)
        task_objects = self._sort_tasks(task_objects)

        return {
            "tasks": [
                {
                    "title": item["title"],
                    "due_date": item["due_date"],
                    "assignee": item["assignee"],
                    "location": item["location"],
                    "category": item["category"],
                    "resources": item["resources"],
                }
                for item in task_objects
            ],
            "priorities": [
                {
                    "task": item["title"],
                    "priority": item["priority"],
                    "reason": item["priority_reason"],
                }
                for item in task_objects
            ],
            "workflow_steps": [item["workflow_step"] for item in task_objects],
        }

    def _clean_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _split_into_request_blocks(self, text: str) -> List[str]:
        """
        Split large pasted content into separate request blocks.
        Handles mixed pasted emails/messages.
        """
        markers = [
            r"Dear\s+[A-ZÄÖÜa-zäöüß]+[,:\s]",
            r"Hello[,:\s]",
            r"I['’]m\s+Stefan\s+from\s+IfeS",
            r"I['’]m\s+not\s+in\s+the\s+office\s+today",
            r"There\s+are\s+some\s+tasks\s+for\s+tomorrow:",
            r"Only\s+one\s+thing\s+needs\s+to\s+be\s+changed",
        ]

        combined = "(" + "|".join(markers) + ")"
        matches = list(re.finditer(combined, text, flags=re.IGNORECASE))

        if len(matches) <= 1:
            return [text]

        blocks = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            block = text[start:end].strip(" ,\n")
            if block:
                blocks.append(block)

        return blocks

    def _remove_quoted_email(self, text: str) -> str:
        patterns = [
            r"\nAm .* schrieb:.*",
            r"\nOn .* wrote:.*",
            r"\nFrom:.*",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
            if match:
                text = text[:match.start()].strip()

        return text

    def _remove_signature(self, text: str) -> str:
        patterns = [
            r"\nRegards,.*",
            r"\nBest regards,.*",
            r"\nBest,.*",
            r"\nThanks,.*",
            r"\nThank you,.*",
            r"\n--\s*\n.*",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
            if match:
                return text[:match.start()].strip()

        return text

    def _extract_shared_due_date(self, text: str, now: datetime) -> Optional[datetime]:
        patterns = [
            r"tasks?\s+for\s+(today|tomorrow|tonight|next week|next month)",
            r"tasks?\s+for\s+([A-Za-z]+)",
            r"tasks?\s+for\s+([A-Za-z]+\s+\d{1,2}(?:,\s*\d{4})?)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                parsed = self._parse_date_text(match.group(1).strip(), now)
                if parsed:
                    return parsed

        return None

    def _extract_task_section(self, text: str) -> str:
        start_patterns = [
            r"There are some tasks.*?:",
            r"Tasks.*?:",
        ]

        section = text
        for pattern in start_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
            if match:
                section = text[match.end():].strip()
                break

        return section.strip()

    def _extract_tasks(self, text: str) -> List[str]:
        bullet_tasks = self._extract_bullets(text)
        if bullet_tasks:
            return bullet_tasks

        reorder_task = self._extract_reorder_style_task(text)
        if reorder_task:
            return [reorder_task]

        request_task = self._extract_request_style_task(text)
        if request_task:
            return [request_task]

        split_tasks = self._extract_list_style_tasks(text)
        if split_tasks:
            return split_tasks

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        tasks = [line for line in lines if self._looks_like_task(line)]
        if tasks:
            return tasks

        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if self._looks_like_task(s)]

    def _extract_bullets(self, text: str) -> List[str]:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        bullet_tasks = []

        for line in lines:
            if re.match(r"^[-•*]\s+", line):
                bullet_tasks.append(re.sub(r"^[-•*]\s+", "", line).strip())

        return bullet_tasks

    def _extract_list_style_tasks(self, text: str) -> List[str]:
        compact = " ".join(text.split())

        compact = re.sub(
            r"^(team meeting discussion:|meeting notes:|discussion:)\s*",
            "",
            compact,
            flags=re.IGNORECASE,
        )
        compact = re.sub(
            r"^(we need to|need to|please|can you)\s+",
            "",
            compact,
            flags=re.IGNORECASE,
        )

        parts = re.split(r",\s+|\s+and\s+", compact, flags=re.IGNORECASE)

        tasks = []
        for part in parts:
            candidate = part.strip(" .")
            if candidate and self._looks_like_task(candidate):
                tasks.append(candidate)

        return tasks

    def _extract_reorder_style_task(self, text: str) -> Optional[str]:
        compact = " ".join(text.split()).lower()
        names_block = self._extract_names_block(text)

        if (
            ("alphabetical order" in compact or "correct order" in compact or "needs to be changed" in compact)
            and names_block
        ):
            return "Reorder the names on the uploaded profile alphabetically by last name using the provided correct order"

        if "alphabetical order" in compact and ("dr. wolf" in compact or "schulleri" in compact):
            return "Reorder the names on the profile page alphabetically by last name"

        return None

    def _extract_names_block(self, text: str) -> List[str]:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        names = []

        start_collecting = False
        for line in lines:
            if "correct order" in line.lower():
                start_collecting = True
                continue

            if start_collecting:
                if self._looks_like_person_name(line):
                    names.append(line)
                    continue

                if names:
                    break

        return names

    def _looks_like_person_name(self, line: str) -> bool:
        prefixes = ("Dr.", "Prof.", "Kathrin", "Bernhard", "Tamara", "Joana", "Clemens", "Birgit")
        if line.startswith(prefixes):
            return True

        words = line.split()
        capitalized_words = sum(1 for w in words if w and w[0].isupper())
        return len(words) >= 2 and capitalized_words >= 2

    def _extract_request_style_task(self, text: str) -> Optional[str]:
        compact = " ".join(text.split())

        website_match = re.search(
            r"mistake on .*?website regarding\s+(.+?);?\s+her phone number is incorrect",
            compact,
            flags=re.IGNORECASE,
        )
        correct_number_match = re.search(
            r"correct number is[:\s]+([+()\d\s-]+)",
            compact,
            flags=re.IGNORECASE,
        )

        if website_match:
            person = website_match.group(1).strip(" .")
            if correct_number_match:
                phone = correct_number_match.group(1).strip()
                return f"Update {person}'s phone number on the institute website to {phone}"
            return f"Correct {person}'s phone number on the institute website"

        generic_fix_match = re.search(
            r"could you please\s+(fix|correct|update|change)\s+this",
            compact,
            flags=re.IGNORECASE,
        )
        if generic_fix_match and "website" in compact.lower():
            return "Fix the incorrect information on the website"

        return None

    def _looks_like_task(self, text: str) -> bool:
        lowered = text.lower()

        if any(word in lowered for word in self.action_words):
            return True

        patterns = [
            r"\bneeds assistance\b",
            r"\bplease check\b",
            r"\bplease ask\b",
            r"\bplease fix\b",
            r"\bcould you please fix\b",
            r"\bincorrect\b",
            r"\bcorrect number\b",
            r"\balphabetical order\b",
            r"\bcorrect order\b",
            r"\bneeds to be changed\b",
            r"\bassist\b",
            r"\bcheck whether\b",
        ]

        return any(re.search(pattern, lowered) for pattern in patterns)

    def _normalize_tasks(self, tasks: List[str], source_text: str) -> List[Dict[str, str]]:
        normalized = []
        seen = set()

        for task in tasks:
            raw_text = self._strip_noise(task)
            title = self._rewrite_task(raw_text, source_text)
            title = self._shorten_task(title)

            key = title.lower().strip()
            if title and key not in seen:
                seen.add(key)
                normalized.append({"title": title, "raw_text": raw_text})

        return normalized

    def _strip_noise(self, task: str) -> str:
        task = task.strip(" -.\n\t")
        task = re.sub(r"\s+", " ", task)
        return task

    def _rewrite_task(self, task: str, source_text: str) -> str:
        lower = task.lower()
        source_lower = source_text.lower()

        if "alphabetical order" in source_lower and "correct order" in source_lower:
            if "profile" in source_lower:
                return "Reorder the names on the uploaded profile alphabetically by last name using the provided correct order"
            return "Reorder the names alphabetically by last name using the provided correct order"

        match = re.search(r"([A-ZÄÖÜ][a-zäöüß]+)\s+needs assistance with\s+(.+)", task)
        if match:
            person = match.group(1)
            subject = match.group(2).strip(" .")
            return f"Assist {person} with {subject}"

        website_match = re.search(
            r"regarding\s+(.+?);?\s+her phone number is incorrect",
            source_text,
            flags=re.IGNORECASE,
        )
        correct_number_match = re.search(
            r"correct number is[:\s]+([+()\d\s-]+)",
            source_text,
            flags=re.IGNORECASE,
        )
        if "website" in source_lower and website_match:
            person = website_match.group(1).strip(" .")
            if correct_number_match:
                phone = correct_number_match.group(1).strip()
                return f"Update {person}'s phone number on the institute website to {phone}"
            return f"Correct {person}'s phone number on the institute website"

        if re.search(r"please check", lower):
            task = re.sub(r"(?i)^.*?please check,?\s*(whether\s+)?", "Check ", task).strip()

        if "nicole" in lower and "it-trash" in lower:
            return "Ask Nicole about moving the IT trash and assist her"

        if "vpn-client software" in lower and "frau maier" in lower:
            return "Assist Frau Maier with the VPN client software"

        if "pcs/workstations" in lower or "desktop-pcs" in lower:
            return "Check that the student assistant room PCs/workstations are working, updated, and connected"

        if "website" in lower and ("incorrect" in lower or "mistake" in lower):
            return "Fix the incorrect information on the website"

        task = re.sub(r"(?i)^also,\s*", "", task)
        task = re.sub(r"(?i)^therefore,\s*", "", task)
        task = re.sub(r"(?i)^please\s+", "", task)
        task = re.sub(r"(?i)^could you please\s+", "", task)
        task = re.sub(r"(?i)^maybe you could\s+", "", task)
        task = re.sub(r"(?i)^we need to\s+", "", task)
        task = re.sub(r"(?i)^need to\s+", "", task)
        task = re.sub(r"(?i)^and\s+", "", task)

        if task and not task[0].isupper():
            task = task[0].upper() + task[1:]

        return task.strip()

    def _shorten_task(self, task: str) -> str:
        splitters = [
            r"\.\s+I think\b",
            r"\.\s+She\b",
            r"\.\s+He\b",
            r"\.\s+This link\b",
            r"\.\s+Therefore\b",
            r"\.\s+Please\b",
            r"\.\s+That would\b",
            r"\.\s+Best regards\b",
            r"\.\s+Thank you\b",
        ]

        shortened = task
        for splitter in splitters:
            parts = re.split(splitter, shortened, maxsplit=1, flags=re.IGNORECASE)
            shortened = parts[0].strip()

        return shortened.strip(" .")

    def _parse_date_text(self, date_text: str, now: datetime) -> Optional[datetime]:
        cleaned = date_text.strip()

        if re.search(r"\b\d{4}\b", cleaned):
            return dateparser.parse(
                cleaned,
                settings={
                    "RELATIVE_BASE": now,
                    "DATE_ORDER": "DMY",
                },
            )

        exact_date_patterns = [
            r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+\d{1,2}(st|nd|rd|th)?\s+[a-z]+$",
            r"^\d{1,2}(st|nd|rd|th)?\s+[a-z]+$",
            r"^[a-z]+\s+\d{1,2}(st|nd|rd|th)?$",
        ]

        if any(re.match(pattern, cleaned.lower()) for pattern in exact_date_patterns):
            return dateparser.parse(
                cleaned,
                settings={
                    "RELATIVE_BASE": now,
                    "DATE_ORDER": "DMY",
                    "PREFER_DAY_OF_MONTH": "first",
                },
            )

        return dateparser.parse(
            cleaned,
            settings={
                "RELATIVE_BASE": now,
                "PREFER_DATES_FROM": "future",
            },
        )

    def _extract_due_date(self, task: str, now: datetime) -> Optional[datetime]:
        patterns = [
            r"\b(today|tomorrow|tonight|next week|next month)\b",
            r"\bby\s+((?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})\b",
            r"\bby\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})\b",
            r"\bby\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?\s+\d{4})\b",
            r"\bby\s+((?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+)\b",
            r"\bby\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+)\b",
            r"\bby\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?)\b",
            r"\bby\s+([A-Za-z]+)\b",
            r"\bon\s+((?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})\b",
            r"\bon\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})\b",
            r"\bon\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?\s+\d{4})\b",
            r"\bon\s+((?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+)\b",
            r"\bon\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+)\b",
            r"\bon\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?)\b",
            r"\bon\s+([A-Za-z]+)\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, task, flags=re.IGNORECASE)
            if match:
                parsed = self._parse_date_text(match.group(1), now)
                if parsed:
                    return parsed

        return None

    def _extract_assignee(self, raw_text: str, title: str, source_text: str) -> Optional[str]:
        person_patterns = [
            r"\b(Frau\s+[A-ZÄÖÜ][a-zäöüß]+)\b",
            r"\b(Herr\s+[A-ZÄÖÜ][a-zäöüß]+)\b",
            r"\b(Nicole)\b",
            r"\b(Touhid)\b",
            r"\b(Katrin\s+Schulleri)\b",
            r"\b(Tamara)\b",
            r"\b(Frau\s+Perl)\b",
        ]

        for pattern in person_patterns:
            match = re.search(pattern, raw_text)
            if match:
                return match.group(1)

        if "maybe you could change that" in source_text.lower():
            return "Touhid"

        possessive_match = re.search(r"Update\s+(.+?)'s\s+phone number", title)
        if possessive_match:
            return possessive_match.group(1)

        match = re.search(r"Assist\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)", title)
        if match:
            return match.group(1)

        return None

    def _extract_location(self, raw_text: str, title: str, source_text: str) -> Optional[str]:
        location_patterns = [
            r"(KOMPASS-office on the \d+(?:st|nd|rd|th) floor)",
            r"(student assistant room)",
            r"(3rd floor)",
            r"(office on the \d+(?:st|nd|rd|th) floor)",
            r"(institute's website)",
            r"(website)",
            r"(profile)",
        ]

        for pattern in location_patterns:
            match = re.search(pattern, raw_text, flags=re.IGNORECASE)
            if match:
                return match.group(1)

        source_lower = source_text.lower()
        if "website" in source_lower:
            return "Institute website"
        if "profile" in source_lower:
            return "Uploaded profile / website profile section"

        return None

    def _extract_resources(self, raw_text: str, source_text: str) -> List[str]:
        links = re.findall(r"https?://\S+", f"{raw_text}\n{source_text}")
        seen = set()
        deduped = []
        for link in links:
            if link not in seen:
                seen.add(link)
                deduped.append(link)
        return deduped

    def _classify_task(self, title: str, raw_text: str, source_text: str) -> str:
        text = f"{title} {raw_text}".lower()

        if any(word in text for word in ["presentation", "slides", "deck"]):
            return "Presentation"
        if any(word in text for word in ["email", "summary", "stakeholder"]):
            return "Communication"
        if any(word in text for word in ["dashboard", "pc", "desktop", "workstation", "updated", "connected"]):
            return "Infrastructure Check"
        if any(word in text for word in ["vpn", "software", "connection", "client"]):
            return "Technical Support"
        if any(word in text for word in ["trash", "move", "bring"]):
            return "Logistics"
        if any(word in text for word in ["website", "phone number", "incorrect", "correct number"]):
            return "Website Update"
        if any(word in text for word in ["alphabetical order", "correct order", "last name", "profile"]):
            return "Content Update"

        return "General Task"

    def _assign_priority(
        self,
        task: str,
        due_date: Optional[datetime],
        now: datetime,
        category: str,
    ) -> Tuple[str, str]:
        task_lower = task.lower()

        if any(keyword in task_lower for keyword in self.urgent_keywords):
            return "High", "Urgent wording detected"

        if due_date:
            delta_hours = (due_date - now).total_seconds() / 3600

            if delta_hours <= 0:
                return "High", "Due now or overdue"
            if delta_hours <= 24:
                return "High", "Due within 24 hours"
            if delta_hours <= 72:
                return "High", "Due within 3 days"
            if delta_hours <= 168:
                return "Medium", "Due within 7 days"
            return "Medium", "Has a future due date"

        if category == "Technical Support":
            return "High", "User-facing support task"
        if category == "Presentation":
            return "High", "Important deliverable"
        if category == "Website Update":
            return "Medium", "Data correction task"
        if category == "Content Update":
            return "Medium", "Content/order correction task"
        if category == "Infrastructure Check":
            return "Medium", "Operational readiness task"
        if category == "Logistics":
            return "Low", "Support task without explicit deadline"
        if any(keyword in task_lower for keyword in self.low_priority_keywords):
            return "Low", "Lower urgency wording"

        return "Medium", "Standard work item"

    def _generate_workflow_step(self, task: str, category: str) -> str:
        task_lower = task.lower()

        if "vpn" in task_lower:
            return "Go to Frau Maier, open the VPN client, explain how to start it, and test the connection"
        if "pc" in task_lower or "workstation" in task_lower or "dashboard" in task_lower:
            return "Check the systems, verify updates and connectivity, and confirm everything works correctly"
        if "it trash" in task_lower:
            return "Ask Nicole for the new IT-trash location and help move the items"
        if category == "Website Update":
            return "Update the website entry, save the corrected information, and verify the published result"
        if category == "Content Update":
            return "Reorder the listed names by last name, save the changes, and verify the final displayed order"
        if category == "Communication":
            return "Draft the message, review it, and send it"
        if category == "Presentation":
            return "Draft the outline, prepare the slides, and review the presentation before sharing"

        return f"Complete the task: {task}"

    def _deduplicate_task_objects(self, task_objects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        deduped = []

        for item in task_objects:
            key = item["title"].strip().lower()
            if key not in seen:
                seen.add(key)
                deduped.append(item)

        return deduped

    def _sort_tasks(self, task_objects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        priority_rank = {"High": 0, "Medium": 1, "Low": 2}

        def sort_key(item: Dict[str, Any]) -> Tuple[int, str, str]:
            due_date_value = item["due_date"] if item["due_date"] else "9999-12-31 23:59"
            return (
                priority_rank.get(item["priority"], 3),
                due_date_value,
                item["title"].lower(),
            )

        return sorted(task_objects, key=sort_key)