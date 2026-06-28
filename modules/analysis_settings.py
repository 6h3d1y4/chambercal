import streamlit as st
import pandas as pd

from modules.db import (
    get_all_chambers,
    add_chamber,
    update_chamber,
    delete_chamber,
    get_analysis_settings_by_group,
    add_analysis_setting,
    update_analysis_setting,
    delete_analysis_setting,
    log_activity,
)

REQUIRED_CHAMBER_CODES = {
    "m1",
    "m2",
}

REQUIRED_ANALYSIS_SETTING_KEYS = {
    "propane_molar_mass_g_mol",
    "molar_volume_l_mol",
    "o2_stoichiometric_factor",
    "co2_stoichiometric_factor",
    "expected_rq",
    "trim_start_min",
    "trim_end_min",
    "green_limit_percent",
    "yellow_limit_percent",
    "orange_limit_percent",
}


def show_analysis_settings_message():
    """
    Display a saved success/info/error message after the page reruns.

    Why this is needed
    ------------------
    Streamlit reruns the whole script after some actions.

    If we directly write:

        st.success("Saved successfully")
        st.rerun()

    the success message disappears immediately because the page reloads.

    To solve this, we first store the message in st.session_state.
    After the rerun, this function displays the message and then deletes it.
    """
    if "analysis_settings_message" not in st.session_state:
        return

    message_type, message_text = st.session_state.analysis_settings_message

    if message_type == "success":
        st.success(message_text)
    elif message_type == "info":
        st.info(message_text)
    elif message_type == "error":
        st.error(message_text)
    else:
        st.write(message_text)

    del st.session_state.analysis_settings_message

def show_add_chamber_form():
    """
    Display a form that allows an admin to add a new chamber.

    This form is used only for creating new chamber records.

    Editing existing chambers is handled separately in the chamber table.
    Keeping creation and editing separate makes the app easier to understand
    and prevents accidental changes.

    Important:
    ----------
    The chamber_code should match the pattern used in uploaded filenames.

    Example:
        Filename: 200930_propane_10h#1_m2_extracted.txt
        Code:     m2

    Later, the analyzer will use this code to automatically detect which
    chamber was used for a propane test.
    """
    st.markdown("##### Add New Chamber")

    with st.form("add_chamber_form"):
        new_code = st.text_input(
            "Chamber code",
            placeholder="Example: m3",
        )

        new_name = st.text_input(
            "Chamber name",
            placeholder="Example: Chamber 3",
        )

        new_notes = st.text_area(
            "Notes",
            placeholder="Optional notes about this chamber",
        )

        submitted = st.form_submit_button("Add Chamber")

        if submitted:
            # Clean user input before saving.
            # lower() keeps chamber codes consistent, for example M3 becomes m3.
            cleaned_code = new_code.strip().lower()
            cleaned_name = new_name.strip()
            cleaned_notes = new_notes.strip()

            if not cleaned_code or not cleaned_name:
                st.error("Please provide both chamber code and chamber name.")
                return

            chamber_created = add_chamber(
                chamber_code=cleaned_code,
                chamber_name=cleaned_name,
                notes=cleaned_notes,
            )

            if chamber_created:
                log_activity(
                    category="analysis_settings",
                    action="chamber_created",
                    actor_user_id=st.session_state.user_id,
                    actor_username=st.session_state.username,
                    target_type="chamber",
                    target_name=cleaned_code,
                    details=f"Created new chamber '{cleaned_code}'.",
                )

                # Store the success message so it appears after st.rerun().
                # Do NOT manually set active_analysis_settings_tab here.
                # The radio widget already remembers the selected section.
                st.session_state.analysis_settings_message = (
                    "success",
                    f"Chamber '{cleaned_code}' was created successfully."
                )

                st.rerun()
            else:
                st.error("This chamber code already exists.")

def show_chambers_settings():
    """
    Display, edit, disable, and delete chamber information.

    This section is used by the admin to manage the metabolic chambers
    available for propane test analysis.

    The chamber_code is important because the app will later detect the
    chamber automatically from uploaded filenames.

    Example filename:
        200930_propane_10h#1_m2_extracted.txt

    In this case:
        m2 → Chamber 2

    What the admin can edit:
        - Chamber name
        - Active/inactive status
        - Notes

    What the admin can delete:
        - Custom/test chambers

    What the admin cannot delete:
        - Protected/default chambers such as m1 and m2

    Reason:
        The analyzer may later depend on the default chamber codes.
    """
    st.markdown("#### Chambers")

    st.write(
        "Manage the available metabolic chambers. "
        "The chamber code is used later to detect the chamber from uploaded filenames."
    )

    chambers = get_all_chambers()

    if not chambers:
        st.info("No chambers found.")

        st.divider()
        show_add_chamber_form()
        return

    chamber_table = []

    for chamber in chambers:
        chamber_code = chamber["chamber_code"]

        is_protected = chamber_code in REQUIRED_CHAMBER_CODES

        chamber_table.append(
            {
                "Chamber ID": chamber["chamber_id"],
                "Code": chamber_code,
                "Name": chamber["chamber_name"],
                "Active": bool(chamber["is_active"]),
                "Notes": chamber["notes"] if chamber["notes"] else "",
                "Protected": is_protected,
                "Delete?": False,
                "Updated At": chamber["updated_at"],
            }
        )

    chamber_df = pd.DataFrame(chamber_table)

    with st.form("chambers_settings_form"):
        edited_chamber_df = st.data_editor(
            chamber_df,
            use_container_width=True,
            hide_index=True,
            disabled=[
                "Chamber ID",
                "Code",
                "Protected",
                "Updated At",
            ],
            column_config={
                "Active": st.column_config.CheckboxColumn(
                    "Active",
                    help="Untick to disable this chamber for future analyses.",
                    default=True,
                ),
                "Protected": st.column_config.CheckboxColumn(
                    "Protected",
                    help="Protected chambers are required by the default setup and cannot be deleted.",
                ),
                "Delete?": st.column_config.CheckboxColumn(
                    "Delete?",
                    help="Tick this only for custom/test chambers you want to delete.",
                    default=False,
                ),
            },
            key="chambers_editor",
        )

        save_chambers = st.form_submit_button("Save Chamber Settings")

    if save_chambers:
        updated_count = 0
        deleted_count = 0
        invalid_rows = []
        protected_delete_attempts = []

        for _, row in edited_chamber_df.iterrows():
            chamber_id = int(row["Chamber ID"])
            chamber_code = str(row["Code"]).strip()
            is_protected = bool(row["Protected"])
            marked_for_delete = bool(row["Delete?"])

            original_row = chamber_df[chamber_df["Chamber ID"] == chamber_id].iloc[0]

            old_name = str(original_row["Name"]).strip()
            old_active = bool(original_row["Active"])
            old_notes = str(original_row["Notes"]).strip()

            new_name = str(row["Name"]).strip()
            new_active = bool(row["Active"])
            new_notes = str(row["Notes"]).strip()

            if marked_for_delete:
                if is_protected:
                    protected_delete_attempts.append(chamber_code)
                    continue

                deleted = delete_chamber(chamber_id)

                if deleted:
                    deleted_count += 1

                    log_activity(
                        category="analysis_settings",
                        action="chamber_deleted",
                        actor_user_id=st.session_state.user_id,
                        actor_username=st.session_state.username,
                        target_type="chamber",
                        target_id=chamber_id,
                        target_name=chamber_code,
                        details=f"Deleted custom chamber '{chamber_code}'.",
                    )

                continue

            if not new_name:
                invalid_rows.append(chamber_code)
                continue

            changed = (
                old_name != new_name
                or old_active != new_active
                or old_notes != new_notes
            )

            if changed:
                updated = update_chamber(
                    chamber_id=chamber_id,
                    chamber_name=new_name,
                    is_active=new_active,
                    notes=new_notes,
                )

                if updated:
                    updated_count += 1

                    log_activity(
                        category="analysis_settings",
                        action="chamber_settings_updated",
                        actor_user_id=st.session_state.user_id,
                        actor_username=st.session_state.username,
                        target_type="chamber",
                        target_id=chamber_id,
                        target_name=chamber_code,
                        details=f"Updated settings for chamber '{chamber_code}'.",
                    )

        if protected_delete_attempts:
            st.warning(
                "These protected chambers were not deleted: "
                + ", ".join(protected_delete_attempts)
            )

        if invalid_rows:
            st.error(
                "Chamber name cannot be empty for: "
                + ", ".join(invalid_rows)
            )

        if updated_count > 0 or deleted_count > 0:
            message_parts = []

            if updated_count > 0:
                message_parts.append(f"{updated_count} chamber setting(s) updated")

            if deleted_count > 0:
                message_parts.append(f"{deleted_count} custom chamber(s) deleted")

            st.session_state.analysis_settings_message = (
                "success",
                " and ".join(message_parts) + " successfully."
            )

            st.rerun()

        elif not protected_delete_attempts and not invalid_rows:
            st.info("No chamber setting changes were made.")

    st.divider()
    show_add_chamber_form()

def show_add_setting_form(setting_group, active_tab_label):
    """
    Display a form that allows an admin to add a new analysis setting.

    Parameters
    ----------
    setting_group : str
        The setting group where the new value should be stored.

        Examples:
            calculation_constant
            trim_setting
            quality_threshold

    active_tab_label : str
        The visible section name in the Analysis Settings page.

        We keep this parameter because the function is called from
        different sections. However, we do not manually write it into
        st.session_state, because the radio widget already manages the
        active section.

    Important design note
    ---------------------
    The analyzer will later depend on some fixed setting keys, such as:
        trim_start_min
        trim_end_min
        expected_rq

    New custom settings can still be added, but the analysis code will
    only use them if we explicitly program it to do so later.
    """
    st.markdown("##### Add New Setting")

    with st.form(f"add_setting_form_{setting_group}"):
        new_key = st.text_input(
            "Setting key",
            placeholder="Example: custom_limit_percent",
            key=f"new_key_{setting_group}",
        )

        new_label = st.text_input(
            "Parameter label",
            placeholder="Example: Custom limit",
            key=f"new_label_{setting_group}",
        )

        new_value = st.number_input(
            "Value",
            value=0.0,
            step=0.1,
            format="%.4f",
            key=f"new_value_{setting_group}",
        )

        new_unit = st.text_input(
            "Unit",
            placeholder="Example: %, min, g/mol",
            key=f"new_unit_{setting_group}",
        )

        new_description = st.text_area(
            "Description",
            placeholder="Explain what this setting is used for.",
            key=f"new_description_{setting_group}",
        )

        submitted = st.form_submit_button("Add Setting")

        if submitted:
            # Clean the user input before saving it.
            cleaned_key = new_key.strip().lower()
            cleaned_label = new_label.strip()
            cleaned_unit = new_unit.strip()
            cleaned_description = new_description.strip()

            if not cleaned_key or not cleaned_label:
                st.error("Please provide both setting key and parameter label.")
                return

            setting_created = add_analysis_setting(
                setting_group=setting_group,
                setting_key=cleaned_key,
                setting_label=cleaned_label,
                setting_value=float(new_value),
                unit=cleaned_unit,
                description=cleaned_description,
            )

            if setting_created:
                log_activity(
                    category="analysis_settings",
                    action="analysis_setting_created",
                    actor_user_id=st.session_state.user_id,
                    actor_username=st.session_state.username,
                    target_type="analysis_setting",
                    target_name=cleaned_key,
                    details=f"Created new analysis setting '{cleaned_key}'.",
                )

                # Store the message so it appears after st.rerun().
                #
                # Do NOT manually set:
                # st.session_state.active_analysis_settings_tab = active_tab_label
                #
                # The radio widget already manages the active section.
                st.session_state.analysis_settings_message = (
                    "success",
                    f"Setting '{cleaned_key}' was created successfully."
                )

                st.rerun()
            else:
                st.error("This setting key already exists.")

def show_settings_group(setting_group, section_title, help_text, active_tab_label):
    """
    Display, edit, and delete one group of analysis settings.

    Parameters
    ----------
    setting_group : str
        Internal database group name.

        Examples:
            calculation_constant
            trim_setting
            quality_threshold

    section_title : str
        Human-readable title shown in the interface.

    help_text : str
        Short explanation shown to the admin.

    active_tab_label : str
        Name of the current settings section.

    Delete behaviour
    ----------------
    Default/core settings are protected and cannot be deleted because the
    analyzer will later depend on their setting keys.

    Custom/test settings can be deleted by ticking the "Delete?" checkbox
    and clicking "Save Changes".

    Why the data editor is inside a form
    ------------------------------------
    Without a form, editing a value in st.data_editor can trigger a
    Streamlit rerun immediately.

    By putting st.data_editor inside st.form(), the edited values are only
    processed when the admin clicks "Save Changes".
    """
    st.markdown(f"#### {section_title}")
    st.write(help_text)

    settings = get_analysis_settings_by_group(setting_group)

    if not settings:
        st.info(f"No settings found for: {setting_group}")

        st.divider()
        show_add_setting_form(setting_group, active_tab_label)
        return

    settings_table = []

    for setting in settings:
        setting_key = setting["setting_key"]

        is_protected = setting_key in REQUIRED_ANALYSIS_SETTING_KEYS

        settings_table.append(
            {
                "Setting ID": setting["setting_id"],
                "Key": setting_key,
                "Parameter": setting["setting_label"],
                "Value": float(setting["setting_value"]),
                "Unit": setting["unit"],
                "Description": setting["description"],
                "Protected": is_protected,
                "Delete?": False,
                "Updated At": setting["updated_at"],
            }
        )

    settings_df = pd.DataFrame(settings_table)

    with st.form(f"{setting_group}_settings_form"):
        edited_settings_df = st.data_editor(
            settings_df,
            use_container_width=True,
            hide_index=True,
            disabled=[
                "Setting ID",
                "Key",
                "Parameter",
                "Unit",
                "Description",
                "Protected",
                "Updated At",
            ],
            column_config={
                "Value": st.column_config.NumberColumn(
                    "Value",
                    help="Edit the numeric value for this setting.",
                    format="%.4f",
                ),
                "Protected": st.column_config.CheckboxColumn(
                    "Protected",
                    help="Protected settings are required by the analysis code and cannot be deleted.",
                ),
                "Delete?": st.column_config.CheckboxColumn(
                    "Delete?",
                    help="Tick this only for custom/test settings you want to delete.",
                    default=False,
                ),
            },
            key=f"{setting_group}_editor",
        )

        save_settings = st.form_submit_button("Save Changes")

    if save_settings:
        updated_count = 0
        deleted_count = 0
        protected_delete_attempts = []
        invalid_value_rows = []

        for _, row in edited_settings_df.iterrows():
            setting_id = int(row["Setting ID"])
            setting_key = str(row["Key"]).strip()
            is_protected = bool(row["Protected"])
            marked_for_delete = bool(row["Delete?"])

            original_row = settings_df[settings_df["Setting ID"] == setting_id].iloc[0]
            old_value = float(original_row["Value"])

            # First handle deletion.
            # If a setting is marked for deletion, we do not also update its value.
            if marked_for_delete:
                if is_protected:
                    protected_delete_attempts.append(setting_key)
                    continue

                deleted = delete_analysis_setting(setting_id)

                if deleted:
                    deleted_count += 1

                    log_activity(
                        category="analysis_settings",
                        action="analysis_setting_deleted",
                        actor_user_id=st.session_state.user_id,
                        actor_username=st.session_state.username,
                        target_type="analysis_setting",
                        target_id=setting_id,
                        target_name=setting_key,
                        details=f"Deleted custom analysis setting '{setting_key}'.",
                    )

                continue

            # Then handle normal value updates.
            new_value = row["Value"]

            if pd.isna(new_value):
                invalid_value_rows.append(setting_key)
                continue

            new_value = float(new_value)

            if new_value != old_value:
                updated = update_analysis_setting(
                    setting_id=setting_id,
                    setting_value=new_value,
                )

                if updated:
                    updated_count += 1

                    log_activity(
                        category="analysis_settings",
                        action="analysis_setting_updated",
                        actor_user_id=st.session_state.user_id,
                        actor_username=st.session_state.username,
                        target_type="analysis_setting",
                        target_id=setting_id,
                        target_name=setting_key,
                        details=(
                            f"Updated setting '{setting_key}' "
                            f"from {old_value} to {new_value}."
                        ),
                    )

        if protected_delete_attempts:
            st.warning(
                "These protected settings were not deleted: "
                + ", ".join(protected_delete_attempts)
            )

        if invalid_value_rows:
            st.error(
                "These settings have invalid/empty values and were not updated: "
                + ", ".join(invalid_value_rows)
            )

        if updated_count > 0 or deleted_count > 0:
            message_parts = []

            if updated_count > 0:
                message_parts.append(f"{updated_count} setting value(s) updated")

            if deleted_count > 0:
                message_parts.append(f"{deleted_count} custom setting(s) deleted")

            st.session_state.analysis_settings_message = (
                "success",
                " and ".join(message_parts) + " successfully."
            )

            st.rerun()

        elif not protected_delete_attempts and not invalid_value_rows:
            st.info("No setting changes were made.")

    st.divider()
    show_add_setting_form(setting_group, active_tab_label)

def show_analysis_settings_tab():
    """
    Display the complete Analysis Settings admin page.

    Important design decision
    -------------------------
    We use a horizontal radio button as a tab selector instead of st.tabs().

    Why?
    ----
    Streamlit tabs often reset to the first tab after st.rerun().

    A radio selector stores its selected value in st.session_state, so
    after saving a setting and rerunning the app, the admin stays in the
    same section.

    Sections:
        1. Chambers
        2. Calculation Constants
        3. Trim Settings
        4. Quality Thresholds
    """
    st.subheader("Analysis Settings")

    st.write(
        "Configure the chamber information and calculation settings used "
        "for propane test analysis."
    )

    # Show success/info/error messages that were stored before st.rerun().
    show_analysis_settings_message()

    section_options = [
        "Chambers",
        "Calculation Constants",
        "Trim Settings",
        "Quality Thresholds",
    ]

    # Initialize the selected section only if it does not exist yet.
    #
    # Important:
    # ----------
    # This is safe because it happens BEFORE the radio widget is created.
    #
    # Do not manually change this key later inside save/add functions,
    # because the radio widget owns this session_state key after creation.
    if "active_analysis_settings_tab" not in st.session_state:
        st.session_state.active_analysis_settings_tab = "Chambers"

    # Safety check:
    # If the stored value is somehow invalid, reset it to Chambers.
    # This prevents errors if we rename or remove a section later.
    if st.session_state.active_analysis_settings_tab not in section_options:
        st.session_state.active_analysis_settings_tab = "Chambers"

    selected_section = st.radio(
        "Analysis settings section",
        options=section_options,
        horizontal=True,
        key="active_analysis_settings_tab",
        label_visibility="collapsed",
    )

    st.divider()

    if selected_section == "Chambers":
        show_chambers_settings()

    elif selected_section == "Calculation Constants":
        show_settings_group(
            setting_group="calculation_constant",
            section_title="Calculation Constants",
            help_text=(
                "These values are used to calculate the theoretical "
                "SOLL VO₂, SOLL VCO₂, and expected RQ from propane combustion."
            ),
            active_tab_label="Calculation Constants",
        )

    elif selected_section == "Trim Settings":
        show_settings_group(
            setting_group="trim_setting",
            section_title="Trim Settings",
            help_text=(
                "These values define how many minutes are excluded from the "
                "beginning and end of the uploaded measurement file before analysis."
            ),
            active_tab_label="Trim Settings",
        )

    elif selected_section == "Quality Thresholds":
        show_settings_group(
            setting_group="quality_threshold",
            section_title="Quality Thresholds",
            help_text=(
                "These thresholds define the colour category based on percentage "
                "deviation from perfect 100% recovery."
            ),
            active_tab_label="Quality Thresholds",
        )